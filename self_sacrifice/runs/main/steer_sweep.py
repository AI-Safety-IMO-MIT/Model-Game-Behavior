"""Dose-response for feature 10590, and a difference-in-means steering vector.

Fixed-first-response version, helped and none, first 100 environments, greedy, layer 30, generated tokens only (as in steer_features.py).
1. Feature 10590 added at k times its median activation, k in STRENGTHS (0 is the unsteered baseline).
2. Difference-in-means vector: mean layer-30 residual over reply tokens (final command excluded) of helped replies that gave, minus those that kept.
   Built from environments 100-199 only, so the steering test on environments 0-99 is held out. Added at alpha times the vector.
   Alignment: cosine with every SAE decoder direction, using a vector built from all 200 environments.
Outputs: steer_sweep.jsonl (replies), diffmean.json (vector norms and alignment), diffmean.pt (vectors)."""
import json, os, sys
import numpy as np
import torch
from huggingface_hub import hf_hub_download
from safetensors.torch import load_file
from transformers import AutoModelForCausalLM, AutoTokenizer
import run_main as rm

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL = "google/gemma-4-31B-it"
REPO, SAE_DIR = "decoderesearch/gemma-4-saes", "gemma-4-31b/btk-mat-layer-30-k-100/"
FEATURE = 10590
STRENGTHS = [0, -8, -4, -2, 1, 2, 4, 8, 16]
ALPHAS = [-2, -1, 1, 2, 4, 8]
BATCH, MAX_NEW = 24, 450


def chat(tok, messages):
    return tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, enable_thinking=False)


def main():
    tok = AutoTokenizer.from_pretrained(MODEL)
    tok.padding_side = "left"
    model = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.bfloat16, device_map={"": 0}).eval()
    w = load_file(hf_hub_download(REPO, SAE_DIR + "sae_weights.safetensors"), device="cuda:0")
    a = np.load(os.path.join(HERE, "sae", "acts.npz"))
    median = float(np.median(a["value"][a["feature"] == FEATURE]))
    del a
    unit = (median * w["W_dec"][FEATURE]).float()
    layer = model.get_submodule([n for n, _ in model.named_modules() if n.endswith("language_model.layers.30")][0])
    state = {"vec": None, "capture": None}

    def hook(_m, _i, output):
        x = output[0] if isinstance(output, tuple) else output
        if state["capture"] is not None:
            state["capture"].append(x.detach().float())
            return output
        if state["vec"] is None or x.shape[1] != 1:
            return output
        h = (x.float() + state["vec"]).to(x.dtype)
        return (h,) + output[1:] if isinstance(output, tuple) else h
    layer.register_forward_hook(hook)

    rows = [json.loads(line) for line in open(os.path.join(HERE, "main_fixed_first_response.jsonl"))]
    helped = [r for r in rows if r["hist"] == "helped"]
    envs = sorted({r["env"] for r in rows})

    # difference in means over reply tokens, final command excluded
    means = {}
    for r in helped:
        cut = r["reply"].rfind("$")
        reply = r["reply"][:cut] if cut > 0 else r["reply"]
        prompt = chat(tok, r["messages"][:4])
        p_ids = tok(prompt, add_special_tokens=False, return_tensors="pt")["input_ids"]
        ids = tok(prompt + reply, add_special_tokens=False, return_tensors="pt")["input_ids"].to(0)
        state["capture"] = []
        with torch.no_grad():
            model(input_ids=ids)
        h = state["capture"][0][0, p_ids.shape[1]:]
        state["capture"] = None
        means[r["id"]] = h.mean(0)
    gave = lambda r: r["gives_to_X"]
    def diff(sub):
        g = torch.stack([means[r["id"]] for r in sub if gave(r)]).mean(0)
        k = torch.stack([means[r["id"]] for r in sub if not gave(r)]).mean(0)
        return g - k, int(sum(map(gave, sub))), int(sum(not gave(r) for r in sub))
    v_all, ng_all, nk_all = diff(helped)
    held = [r for r in helped if r["env"] in envs[100:]]
    v_train, ng_tr, nk_tr = diff(held)
    dec = w["W_dec"].float()
    cos = (dec @ v_all) / (dec.norm(dim=1) * v_all.norm())
    top = torch.topk(cos, 25)
    bottom = torch.topk(-cos, 25)
    resid_norm = float(torch.stack(list(means.values())).norm(dim=1).mean())
    info = {"n_gave_all": ng_all, "n_kept_all": nk_all, "n_gave_train": ng_tr, "n_kept_train": nk_tr,
            "norm_all": float(v_all.norm()), "norm_train": float(v_train.norm()), "mean_residual_norm": resid_norm,
            "norm_10590_unit": float(unit.norm()), "cos_train_all": float(torch.nn.functional.cosine_similarity(v_all, v_train, dim=0)),
            "cos_10590": float(cos[FEATURE]), "cos_10590_rank": int((cos > cos[FEATURE]).sum()) + 1,
            "top": [[int(i), float(c)] for c, i in zip(top.values, top.indices)],
            "bottom": [[int(i), float(-c)] for c, i in zip(bottom.values, bottom.indices)],
            "sae_encode_top": None}
    pre = v_all @ w["W_enc"].float()    # encoder projection of the direction itself, no bias
    info["sae_encode_top"] = [[int(i), float(x)] for x, i in zip(*torch.topk(pre, 25))]
    json.dump(info, open(os.path.join(HERE, "diffmean.json"), "w"), indent=1)
    torch.save({"all": v_all.cpu(), "train": v_train.cpu(), "unit_10590": unit.cpu()}, os.path.join(HERE, "diffmean.pt"))
    print({k: v for k, v in info.items() if not isinstance(v, list)}, flush=True)

    test = [r for r in rows if r["env"] in envs[:100] and r["hist"] in ("helped", "none")]
    conditions = [(f"f10590_x{k}", k * unit) for k in STRENGTHS] + [(f"diffmean_a{al}", al * v_train) for al in ALPHAS]
    out = os.path.join(HERE, "steer_sweep.jsonl")
    done = {(r["condition"], r["id"]) for r in map(json.loads, open(out))} if os.path.exists(out) else set()
    with open(out, "a") as fh:
        for label, vec in conditions:
            state["vec"] = vec if label != "f10590_x0" else None
            todo = [r for r in test if (label, r["id"]) not in done]
            for s in range(0, len(todo), BATCH):
                batch = todo[s:s + BATCH]
                enc = tok([chat(tok, r["messages"][:4]) for r in batch], return_tensors="pt", padding=True, add_special_tokens=False).to(0)
                with torch.no_grad():
                    out_ids = model.generate(**enc, max_new_tokens=MAX_NEW, do_sample=False, temperature=None, top_p=None, top_k=None)
                for r, ids in zip(batch, out_ids[:, enc["input_ids"].shape[1]:]):
                    reply = tok.decode(ids, skip_special_tokens=True)
                    decision, target = rm.parse(reply)
                    fh.write(json.dumps({"id": r["id"], "env": r["env"], "hist": r["hist"], "condition": label, "reply": reply, "decision": decision,
                                         "gives_to_X": decision == "give" and target == r["X"], "original_gave": r["gives_to_X"]}) + "\n")
                fh.flush()
                print(label, s + len(batch), flush=True)


if __name__ == "__main__":
    main()
