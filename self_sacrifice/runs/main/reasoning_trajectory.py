"""How does the decision form across the reasoning?

Fixed-first-response version, all 800 conversations. The model's own reasoning is cut after each sentence, including after zero sentences, `Decision: $` is
appended, and we read log-odds of give vs pass at the next token. The model's own text is replayed unchanged, so nothing is resampled.
Output: reasoning_trajectory.jsonl, one record per conversation."""
import json, os, re
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL = "google/gemma-4-31B-it"
GIVE, PASS = 2583, 1786


def reasoning_of(reply):
    """the reply up to its last command"""
    m = list(re.finditer(r"`?\$\s*(give|pass)\b", reply, re.I))
    return reply[:m[-1].start()].rstrip() if m else None


def sentences(text):
    return [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]


def main():
    tok = AutoTokenizer.from_pretrained(MODEL)
    model = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.bfloat16, device_map={"": 0}).eval()
    rows = [json.loads(line) for line in open(os.path.join(HERE, "main_fixed_first_response.jsonl"))]
    path = os.path.join(HERE, "reasoning_trajectory.jsonl")
    with open(path, "w") as fh:
        for n, r in enumerate(rows):
            base = tok.apply_chat_template(r["messages"], tokenize=False, add_generation_prompt=True, enable_thinking=False)
            parts = sentences(reasoning_of(r["reply"]) or "")
            scores = []
            for k in range(len(parts) + 1):
                prefix = " ".join(parts[:k])
                text = base + (prefix + "\n\n" if prefix else "") + "Decision: $"
                enc = tok(text, return_tensors="pt", add_special_tokens=False).to(0)
                with torch.no_grad():
                    logits = model(**enc, use_cache=False).logits[0, -1].float()
                lp = torch.log_softmax(logits, -1)
                scores.append(round(float(lp[GIVE] - lp[PASS]), 3))
            fh.write(json.dumps({"id": r["id"], "env": r["env"], "hist": r["hist"], "gave": r["gives_to_X"], "decision": r["decision"],
                                 "sentences": parts, "scores": scores}) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
            print(n + 1, len(parts), flush=True)


if __name__ == "__main__":
    main()
