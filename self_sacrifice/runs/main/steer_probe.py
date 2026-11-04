"""What does the specific RL vector encode? Greedy, layer 30, generated tokens only, environments 0-99 (the held-out test set).

1. Transfer: the vector on histories it never saw in training. Main scenario: bystander (X helped another agent) and rescued (X was rescued by others).
   Repair scenario (the favour hands nothing over): all four histories. Each against an unsteered baseline run the same way.
2. Decomposition on helped and none: the vector's component along 10590 alone, and the remainder alone.
   Also the tokens each part promotes when read directly through the unembedding.
Outputs: steer_probe.jsonl (replies), steer_probe.json (decomposition and token readout)."""
import json, os
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
import run_main as rm

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL = "google/gemma-4-31B-it"
BATCH, MAX_NEW = 24, 450


def chat(tok, messages):
    return tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, enable_thinking=False)


def main():
    tok = AutoTokenizer.from_pretrained(MODEL)
    tok.padding_side = "left"
    model = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.bfloat16, device_map={"": 0}).eval()
    v = torch.load(os.path.join(HERE, "steer_rl_f10590_specific.pt")).float().to(0)
    unit = torch.load(os.path.join(HERE, "diffmean.pt"))["unit_10590"].float().to(0)
    d = unit / unit.norm()
    proj = (v @ d) * d
    rest = v - proj
    W = model.get_output_embeddings().weight.float()
    read = lambda x, k=15: [tok.decode([int(i)]) for i in torch.topk(W @ x, k).indices]
    info = {"norm_v": float(v.norm()), "norm_proj": float(proj.norm()), "norm_rest": float(rest.norm()), "proj_in_10590_units": float(v @ d / unit.norm()),
            "tokens_up": {"v": read(v), "proj": read(proj), "rest": read(rest)}, "tokens_down": {"v": read(-v), "proj": read(-proj), "rest": read(-rest)}}
    json.dump(info, open(os.path.join(HERE, "steer_probe.json"), "w"), indent=1, ensure_ascii=False)
    print(info, flush=True)

    layer = model.get_submodule([n for n, _ in model.named_modules() if n.endswith("language_model.layers.30")][0])
    state = {"vec": None}

    def hook(_m, _i, output):
        x = output[0] if isinstance(output, tuple) else output
        if state["vec"] is None or x.shape[1] != 1:
            return output
        h = (x.float() + state["vec"]).to(x.dtype)
        return (h,) + output[1:] if isinstance(output, tuple) else h
    layer.register_forward_hook(hook)

    main_rows = [json.loads(line) for line in open(os.path.join(HERE, "main_fixed_first_response.jsonl"))]
    repair_rows = [json.loads(line) for line in open(os.path.join(HERE, "repair_fixed.jsonl"))]
    envs = sorted({r["env"] for r in main_rows})[:100]
    pick = lambda rows, hists: [r for r in rows if r["env"] in envs and r["hist"] in hists]
    transfer = pick(main_rows, ("bystander", "rescued")) + pick(repair_rows, ("repaired", "repair_bystander", "repair_rescued", "repair_none"))
    decomp = pick(main_rows, ("helped", "none"))
    jobs = [("baseline", None, transfer), ("rl_specific", v, transfer), ("proj_10590", proj, decomp), ("remainder", rest, decomp)]
    out = os.path.join(HERE, "steer_probe.jsonl")
    done = {(r["condition"], r["id"]) for r in map(json.loads, open(out))} if os.path.exists(out) else set()
    with open(out, "a") as fh:
        for label, vec, rows in jobs:
            state["vec"] = vec
            todo = [r for r in rows if (label, r["id"]) not in done]
            for s in range(0, len(todo), BATCH):
                batch = todo[s:s + BATCH]
                enc = tok([chat(tok, r["messages"][:4]) for r in batch], return_tensors="pt", padding=True, add_special_tokens=False).to(0)
                with torch.no_grad():
                    ids_all = model.generate(**enc, max_new_tokens=MAX_NEW, do_sample=False, temperature=None, top_p=None, top_k=None)
                for r, ids in zip(batch, ids_all[:, enc["input_ids"].shape[1]:]):
                    reply = tok.decode(ids, skip_special_tokens=True)
                    decision, target = rm.parse(reply)
                    fh.write(json.dumps({"id": r["id"], "env": r["env"], "hist": r["hist"], "condition": label, "reply": reply, "decision": decision,
                                         "target": target, "gives_to_X": decision == "give" and target == r["X"], "original_gave": r["gives_to_X"]}) + "\n")
                fh.flush()
                print(label, s + len(batch), flush=True)


if __name__ == "__main__":
    main()
