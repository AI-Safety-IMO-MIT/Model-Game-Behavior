"""Save residual-stream activations for every conversation before any reasoning, for the linear probes.

Runs Gemma-4-31B in bf16 with transformers and hooks each decoder layer's output. For each conversation it saves two positions:
  last   the last prompt token, right before the reply would start
  history  mean over the tokens of the final user message
Layers: every sixth layer, which are the global-attention layers, plus layer 1 as a floor.
Output: activations/<version>.npz with arrays of shape (items, layers, positions, d_model), and matching ids."""
import json, os, sys
import numpy as np
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL = "google/gemma-4-31B-it"
LAYERS = [1, 6, 12, 18, 24, 30, 36, 42, 48, 54, 60]    # 1-indexed
BATCH = 1    # one conversation at a time, so padding cannot change the values


def text_layers(model):
    for name, module in model.named_modules():
        if name.endswith(".layers") and len(module) == 60:
            return module
    raise RuntimeError("no 60-layer stack found")


def main():
    tok = AutoTokenizer.from_pretrained(MODEL)
    tok.padding_side = "left"
    model = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.bfloat16, device_map={"": 0}).eval()
    stack = text_layers(model)
    grabbed = {}

    def hook(i):
        def fn(_module, _inputs, output):
            grabbed[i] = (output[0] if isinstance(output, tuple) else output).detach()
        return fn
    for i in LAYERS:
        stack[i - 1].register_forward_hook(hook(i))
    os.makedirs(os.path.join(HERE, "activations"), exist_ok=True)
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    for name, version in [("main_fixed_first_response.jsonl", "main-fixed-first-response"), ("main.jsonl", "main")]:
        rows = [json.loads(line) for line in open(os.path.join(HERE, name))][:limit]
        out = np.zeros((len(rows), len(LAYERS), 2, model.config.get_text_config().hidden_size), dtype=np.float32)
        lengths = []
        for start in range(0, len(rows), BATCH):
            batch = rows[start:start + BATCH]
            texts = [tok.apply_chat_template(r["messages"], tokenize=False, add_generation_prompt=True, enable_thinking=False) for r in batch]
            assert all(t.endswith("<|channel>thought\n<channel|>") for t in texts)    # same empty thought block that vLLM rendered
            enc = tok(texts, return_tensors="pt", padding=True, add_special_tokens=False).to(0)
            with torch.no_grad():
                model(**enc, use_cache=False)
            for b, text in enumerate(texts):
                ids = enc["input_ids"][b]
                keep = enc["attention_mask"][b].bool()
                marker = tok.encode("<|turn>user", add_special_tokens=False)[0]
                starts = (ids == marker).nonzero().flatten()
                first = int(starts[-2])    # starts[-1] opens the model's turn; starts[-2] opens the final user message
                lengths.append(int(keep.sum()))
                for li, layer in enumerate(LAYERS):
                    h = grabbed[layer][b]
                    out[start + b, li, 0] = h[-1].float().cpu().numpy()
                    out[start + b, li, 1] = h[first:-1].float().mean(0).cpu().numpy()
            print(version, start + len(batch), "/", len(rows), flush=True)
        np.savez(os.path.join(HERE, "activations", version + ".npz"), x=out, ids=np.array([r["id"] for r in rows]), layers=np.array(LAYERS))
        print("saved", version, out.shape, "max length", max(lengths), flush=True)


if __name__ == "__main__":
    main()
