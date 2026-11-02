"""Do the SAE features drive the decision? Steer them while the model writes its reply.

Fixed-first-response version, helped and none, first 100 environments. At the SAE's layer, on generated tokens only, each condition either adds a feature set's decoder
directions or removes those features' own activations. Added strength is twice the feature's typical activation in our data. Greedy, so differences come from steering.
Output: steer_features.jsonl."""
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
SETS = {"reciprocity": [11638, 3337, 17978, 10590], "no_basis": [10885, 2093, 2891, 81026]}
SCREEN = len(sys.argv) > 1 and sys.argv[1] == "screen"    # each of the top 100 ranked features alone, added; resumes from steer_screen.jsonl
ROUND3 = len(sys.argv) > 1 and sys.argv[1] == "round3"    # the reciprocity set, one feature at a time
ROUND2 = len(sys.argv) > 1 and sys.argv[1] == "round2"    # labelled pair, plus placebo sets of random features at the same strength
BATCH, MAX_NEW = 12, 450


def main():
    tok = AutoTokenizer.from_pretrained(MODEL)
    tok.padding_side = "left"
    model = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.bfloat16, device_map={"": 0}).eval()
    w = load_file(hf_hub_download(REPO, SAE_DIR + "sae_weights.safetensors"), device="cuda:0")
    a = np.load(os.path.join(HERE, "sae", "acts.npz"))
    if SCREEN:
        SETS.clear()
        SETS.update({str(r["feature"]): [r["feature"]] for r in json.load(open(os.path.join(HERE, "sae_rank_simple.json")))[:100]})
    if ROUND2:
        reply = a["section"][a["token"]] == 1
        conv_rate = np.bincount(a["feature"][reply], minlength=131072) / reply.sum()
        pool = np.where((conv_rate > 1e-3) & (conv_rate < 1e-2))[0]
        pool = np.array([f for f in pool if f not in sum(SETS.values(), [])])
        rng = np.random.default_rng(0)
        SETS.clear()
        SETS["labelled"] = [11638, 77666]
        SETS["placebo_a"] = [int(x) for x in rng.choice(pool, 4, replace=False)]
        SETS["placebo_b"] = [int(x) for x in rng.choice(pool, 4, replace=False)]
        print("sets", SETS, flush=True)
    typical = {}
    for f in sum(SETS.values(), []):
        v = a["value"][a["feature"] == f]
        typical[f] = float(np.median(v))
    print("typical activations", typical, flush=True)
    del a

    state = {"mode": None, "feats": None}

    def hook(_m, _i, output):
        x = output[0] if isinstance(output, tuple) else output
        if state["mode"] is None or x.shape[1] != 1:    # steer generated tokens only, not the prompt pass
            return output
        h = x.float()
        f = torch.tensor(state["feats"], device=h.device)
        if state["mode"] == "add":
            strength = torch.tensor([2 * typical[i] for i in state["feats"]], device=h.device)
            h = h + strength @ w["W_dec"][f]
        else:
            pre = (h - w["b_dec"]) @ w["W_enc"][:, f] + w["b_enc"][f]
            acts = pre * (pre > w["threshold"][f])
            h = h - acts @ w["W_dec"][f]
        h = h.to(x.dtype)
        return (h,) + output[1:] if isinstance(output, tuple) else h
    name = [n for n, _ in model.named_modules() if n.endswith("language_model.layers.30")][0]
    model.get_submodule(name).register_forward_hook(hook)

    rows = [json.loads(line) for line in open(os.path.join(HERE, "main_fixed_first_response.jsonl"))]
    envs = sorted({r["env"] for r in rows})[:100]
    rows = [r for r in rows if r["env"] in envs and r["hist"] in ("helped", "none")]
    conditions = [("baseline", None, None)] + [(f"{k}_{m}", m, v) for k, v in SETS.items() for m in ("add", "remove")]
    if SCREEN:
        conditions = [(f"f{k}_add", "add", v) for k, v in SETS.items()]
    if ROUND3:
        conditions = [("past_3337_add", "add", [3337]), ("stance_17978_add", "add", [17978]), ("pronoun_10590_add", "add", [10590]),
                      ("three_without_11638_add", "add", [3337, 17978, 10590]), ("full_set_repeat_add", "add", [11638, 3337, 17978, 10590])]
    if ROUND2:
        conditions = [("labelled_add", "add", SETS["labelled"]), ("labelled_remove", "remove", SETS["labelled"]),
                      ("placebo_a_add", "add", SETS["placebo_a"]), ("placebo_b_add", "add", SETS["placebo_b"])]
    path = "steer_screen.jsonl" if SCREEN else None
    done = set()
    if SCREEN and os.path.exists(os.path.join(HERE, path)):
        done = {(r["condition"], r["id"]) for r in map(json.loads, open(os.path.join(HERE, path)))}
    with open(os.path.join(HERE, path or ("steer_features3.jsonl" if ROUND3 else "steer_features2.jsonl" if ROUND2 else "steer_features.jsonl")), "a" if SCREEN else "w") as fh:
        for label, mode, feats in conditions:
            state.update(mode=mode, feats=feats)
            todo = [r for r in rows if (label, r["id"]) not in done]
            for s in range(0, len(todo), BATCH):
                batch = todo[s:s + BATCH]
                texts = [tok.apply_chat_template(r["messages"], tokenize=False, add_generation_prompt=True, enable_thinking=False) for r in batch]
                enc = tok(texts, return_tensors="pt", padding=True, add_special_tokens=False).to(0)
                with torch.no_grad():
                    out = model.generate(**enc, max_new_tokens=MAX_NEW, do_sample=False, temperature=None, top_p=None, top_k=None)
                for r, ids in zip(batch, out[:, enc["input_ids"].shape[1]:]):
                    reply = tok.decode(ids, skip_special_tokens=True)
                    decision, target = rm.parse(reply)
                    fh.write(json.dumps({"id": r["id"], "env": r["env"], "hist": r["hist"], "condition": label, "reply": reply, "decision": decision,
                                         "gives_to_X": decision == "give" and target == r["X"], "original_gave": r["gives_to_X"]}) + "\n")
                fh.flush()
                print(label, s + len(batch), flush=True)


if __name__ == "__main__":
    main()
