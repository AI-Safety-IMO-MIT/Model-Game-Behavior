"""Run the pre-trained Gemma SAE over the fixed-first-response conversations.

SAE: decoderesearch/gemma-4-saes, gemma-4-31b/btk-mat-layer-30-k-100. It hooks model.language_model.layers.30, the 31st layer, and was trained on the base model
on Pile text. We run the -it model in bf16 on the full conversation including the model's own reply, and encode tokens from the final user message onwards.
Encoding is the SAE's own: (x - b_dec) @ W_enc + b_enc, kept where it exceeds the per-feature threshold (jumprelu).
Output: sae/acts.npz with sparse (token, feature, value) triples and token metadata, plus reconstruction quality."""
import json, os, sys
import numpy as np
import torch
from huggingface_hub import hf_hub_download
from safetensors.torch import load_file
from transformers import AutoModelForCausalLM, AutoTokenizer

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL = "google/gemma-4-31B-it"
REPO, SAE_DIR = "decoderesearch/gemma-4-saes", "gemma-4-31b/btk-mat-layer-30-k-100/"
LAYER_INDEX = 30


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    tok = AutoTokenizer.from_pretrained(MODEL)
    model = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.bfloat16, device_map={"": 0}).eval()
    names = [n for n, _ in model.named_modules() if n.endswith("language_model.layers.30")]
    assert len(names) == 1, names
    print("hooking", names[0], flush=True)
    grabbed = {}
    model.get_submodule(names[0]).register_forward_hook(
        lambda _m, _i, o: grabbed.__setitem__("x", (o[0] if isinstance(o, tuple) else o).detach()))
    w = load_file(hf_hub_download(REPO, SAE_DIR + "sae_weights.safetensors"), device="cuda:0")
    rows = [json.loads(line) for line in open(os.path.join(HERE, "main_fixed_first_response.jsonl"))][:limit]
    marker = tok.encode("<|turn>user", add_special_tokens=False)[0]
    t_idx, f_idx, vals = [], [], []
    conv, section, text, n_tok = [], [], [], 0
    sse = sst = 0.0
    x_sum, x_count = 0, 0
    active = []
    for i, r in enumerate(rows):
        prompt = tok.apply_chat_template(r["messages"], tokenize=False, add_generation_prompt=True, enable_thinking=False)
        p_len = len(tok(prompt, add_special_tokens=False)["input_ids"])
        enc = tok(prompt + r["reply"], return_tensors="pt", add_special_tokens=False).to(0)
        with torch.no_grad():
            model(**enc, use_cache=False)
            ids = enc["input_ids"][0]
            first = int((ids[:p_len] == marker).nonzero().flatten()[-2])
            x = grabbed["x"][0, first:].float()
            pre = (x - w["b_dec"]) @ w["W_enc"] + w["b_enc"]
            acts = pre * (pre > w["threshold"])
            recon = acts @ w["W_dec"] + w["b_dec"]
            sse += float(((x - recon) ** 2).sum())
            x_sum = x_sum + x.sum(0)
            x_count += x.shape[0]
            sst += float((x ** 2).sum())
            active.append(float((acts > 0).sum(1).float().mean()))
            nz = acts.nonzero()
        t_idx.append((nz[:, 0] + n_tok).cpu().numpy())
        f_idx.append(nz[:, 1].cpu().numpy())
        vals.append(acts[nz[:, 0], nz[:, 1]].cpu().numpy())
        tokens = tok.convert_ids_to_tokens(ids[first:].tolist())
        conv += [i] * len(tokens)
        section += [0 if first + j < p_len else 1 for j in range(len(tokens))]
        text += tokens
        n_tok += len(tokens)
        if i % 50 == 0:
            print(i, n_tok, round(np.mean(active), 1), flush=True)
    os.makedirs(os.path.join(HERE, "sae"), exist_ok=True)
    mean = (x_sum / x_count)
    total_var = sst - x_count * float((mean ** 2).sum())
    quality = {"tokens": n_tok, "mean_active_features": float(np.mean(active)), "explained_variance": 1 - sse / total_var}
    json.dump(quality, open(os.path.join(HERE, "sae", "quality.json"), "w"), indent=2)
    print(quality, flush=True)
    np.savez(os.path.join(HERE, "sae", "acts.npz"), token=np.concatenate(t_idx), feature=np.concatenate(f_idx), value=np.concatenate(vals),
             conv=np.array(conv), section=np.array(section), text=np.array(text), ids=np.array([r["id"] for r in rows]),
             hist=np.array([r["hist"] for r in rows]), env=np.array([r["env"] for r in rows]), gave=np.array([r["gives_to_X"] for r in rows]))


if __name__ == "__main__":
    main()
