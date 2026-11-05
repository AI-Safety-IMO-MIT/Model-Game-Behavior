"""How far can a steering vector push giving? Train the vector itself with reinforcement learning; the model stays frozen.

python steer_rl.py [init] [specific]    init: f10590 (default; 2x its median, the strength that worked) | diffmean | zero
With "specific", half of each batch is no-history prompts, rewarded for reaching a decision that does not give to X, so the vector must stay specific to the benefactor.

Policy: Gemma-4-31B with vector v added at layer 30 on generated tokens (as in steer_features.py), sampling at temperature 1.
Reward: 1 if the reply gives the last life to X, the agent that helped, else 0. Train on helped prompts from environments 100-199 only.
Update: REINFORCE with a leave-one-out baseline over 4 samples per prompt; gradient flows only into v.
Test: greedy on environments 0-99, helped and none, with the final v; the none rate shows whether the vector is specific to the benefactor.
Outputs: steer_rl_<init>_train.jsonl, steer_rl_<init>_eval.jsonl, steer_rl_<init>.pt."""
import json, math, os, random, sys
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
import run_main as rm

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL = "google/gemma-4-31B-it"
INIT = sys.argv[1] if len(sys.argv) > 1 else "f10590"
SPECIFIC = len(sys.argv) > 2 and sys.argv[2] == "specific"
TAG = INIT + ("_specific" if SPECIFIC else "")
STEPS, PROMPTS, SAMPLES, MAX_NEW, EVAL_BATCH = 25, 8, 4, 450, 24


def chat(tok, messages):
    return tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, enable_thinking=False)


def main():
    random.seed(0)
    torch.manual_seed(0)
    tok = AutoTokenizer.from_pretrained(MODEL)
    tok.padding_side = "left"
    model = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.bfloat16, device_map={"": 0}).eval()
    for p in model.parameters():
        p.requires_grad_(False)
    vecs = torch.load(os.path.join(HERE, "diffmean.pt"))
    unit = vecs["unit_10590"].to(0)
    init = {"f10590": 2 * unit, "diffmean": vecs["train"].to(0), "zero": torch.zeros_like(unit)}[INIT]
    v = torch.nn.Parameter(init.clone())
    scale = float((2 * unit).norm())
    opt = torch.optim.Adam([v], lr=0.1 * scale / math.sqrt(v.numel()))
    layer = model.get_submodule([n for n, _ in model.named_modules() if n.endswith("language_model.layers.30")][0])
    state = {"mode": "generate", "start": None}

    def hook(_m, _i, output):
        x = output[0] if isinstance(output, tuple) else output
        if state["mode"] == "generate":
            if x.shape[1] != 1:
                return output
            h = (x.float() + v.detach()).to(x.dtype)
        else:    # teacher forcing: steer the reply positions, which generation steered too
            mask = torch.zeros(x.shape[1], 1, device=x.device)
            mask[state["start"]:] = 1
            h = (x.float() + mask * v).to(x.dtype)
        return (h,) + output[1:] if isinstance(output, tuple) else h
    layer.register_forward_hook(hook)

    rows = [json.loads(line) for line in open(os.path.join(HERE, "main_fixed_first_response.jsonl"))]
    envs = sorted({r["env"] for r in rows})
    train = [r for r in rows if r["env"] in envs[100:] and r["hist"] == "helped"]
    train_none = [r for r in rows if r["env"] in envs[100:] and r["hist"] == "none"]
    test = [r for r in rows if r["env"] in envs[:100] and r["hist"] in ("helped", "none")]
    log = open(os.path.join(HERE, f"steer_rl_{TAG}_train.jsonl"), "w")

    for step in range(STEPS):
        batch = random.sample(train, PROMPTS // 2) + random.sample(train_none, PROMPTS // 2) if SPECIFIC else random.sample(train, PROMPTS)
        texts = [chat(tok, r["messages"]) for r in batch for _ in range(SAMPLES)]
        enc = tok(texts, return_tensors="pt", padding=True, add_special_tokens=False).to(0)
        state["mode"] = "generate"
        with torch.no_grad():
            out = model.generate(**enc, max_new_tokens=MAX_NEW, do_sample=True, temperature=1.0, top_p=1.0, top_k=0)
        replies = out[:, enc["input_ids"].shape[1]:]
        rewards, items = [], []
        for i, ids in enumerate(replies):
            r = batch[i // SAMPLES]
            ids = ids[ids != tok.pad_token_id]
            text = tok.decode(ids, skip_special_tokens=True)
            decision, target = rm.parse(text)
            gave = decision == "give" and target == r["X"]
            rewards.append(float(gave) if r["hist"] == "helped" else float(decision is not None and not gave))
            items.append((r, ids, text, decision))
        R = torch.tensor(rewards).view(PROMPTS, SAMPLES)
        adv = (R - (R.sum(1, keepdim=True) - R) / (SAMPLES - 1)).view(-1)
        opt.zero_grad()
        state["mode"] = "train"
        n = 0
        for (r, ids, _, _), a in zip(items, adv):
            if a == 0 or len(ids) < 2:
                continue
            p_ids = tok(chat(tok, r["messages"]), add_special_tokens=False, return_tensors="pt")["input_ids"].to(0)
            full = torch.cat([p_ids[0], ids]).unsqueeze(0)
            state["start"] = p_ids.shape[1]
            logits = model(input_ids=full, logits_to_keep=len(ids) + 1).logits[0, :-1].float()
            logp = torch.log_softmax(logits, -1).gather(1, ids.unsqueeze(1)).squeeze(1)
            loss = -(a.to(0) * logp[1:].mean()) / (PROMPTS * SAMPLES)    # token 0 comes before any steering
            loss.backward()
            n += 1
            del logits, logp, loss
        if n:
            opt.step()
        rec = {"step": step, "reward": float(R.mean()), "updated_on": n, "norm": float(v.norm()), "norm_init": float(init.norm()),
               "cos_init": float(torch.nn.functional.cosine_similarity(v.detach(), init, dim=0)) if init.norm() > 0 else None,
               "cos_10590": float(torch.nn.functional.cosine_similarity(v.detach(), unit, dim=0)),
               "cos_diffmean": float(torch.nn.functional.cosine_similarity(v.detach(), vecs["train"].to(0), dim=0)),
               "reward_helped": float(R[:PROMPTS // 2].mean()) if SPECIFIC else None, "reward_none": float(R[PROMPTS // 2:].mean()) if SPECIFIC else None,
               "samples": [{"id": it[0]["id"], "reply": it[2], "decision": it[3], "reward": rw} for it, rw in zip(items, rewards)]}
        log.write(json.dumps(rec) + "\n")
        log.flush()
        print({k: x for k, x in rec.items() if k != "samples"}, flush=True)
        torch.save(v.detach().cpu(), os.path.join(HERE, f"steer_rl_{TAG}.pt"))

    state["mode"] = "generate"
    with open(os.path.join(HERE, f"steer_rl_{TAG}_eval.jsonl"), "w") as fh:
        for s in range(0, len(test), EVAL_BATCH):
            batch = test[s:s + EVAL_BATCH]
            enc = tok([chat(tok, r["messages"]) for r in batch], return_tensors="pt", padding=True, add_special_tokens=False).to(0)
            with torch.no_grad():
                out = model.generate(**enc, max_new_tokens=MAX_NEW, do_sample=False, temperature=None, top_p=None, top_k=None)
            for r, ids in zip(batch, out[:, enc["input_ids"].shape[1]:]):
                reply = tok.decode(ids, skip_special_tokens=True)
                decision, target = rm.parse(reply)
                fh.write(json.dumps({"id": r["id"], "env": r["env"], "hist": r["hist"], "condition": f"rl_{TAG}", "reply": reply, "decision": decision,
                                     "gives_to_X": decision == "give" and target == r["X"], "original_gave": r["gives_to_X"]}) + "\n")
            fh.flush()
            print("eval", s + len(batch), flush=True)


if __name__ == "__main__":
    main()
