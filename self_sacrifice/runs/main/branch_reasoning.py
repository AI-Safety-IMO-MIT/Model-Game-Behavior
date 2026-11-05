"""Where does the decision lock in? Branch from the model's reasoning and resample what comes next.

Fixed-first-response version. Takes every give in helped, bystander and none, with the same number of random keeps from that history. Each reply is cut after
0 to 5 sentences and continued 10 times at temperature 0.7. This is the one step that samples: greedy decoding would return the same continuation.
Output: branch_reasoning.jsonl, one record per conversation and cut."""
import json, os, random, re, sys
from concurrent.futures import ThreadPoolExecutor
import requests
from reasoning_trajectory_text import reasoning_of, sentences

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = "http://localhost:8000"
MODEL = "gemma-4-31b"
SAMPLES, TEMPERATURE, MAX_CUT = 10, 0.7, 5
COMMAND = re.compile(r"\$\s*(?:(give)\s+(\w+)\s+(\d+)|(pass)\b)", re.I)


def outcome(text, X):
    found = COMMAND.findall(text.replace("<agent>", ""))
    if not found:
        return "none"
    _, target, _, nothing = found[-1]
    return "keep" if nothing else ("give" if target.capitalize() == X else "other")


def one(job):
    r, k, parts = job
    ids = requests.post(f"{BASE}/tokenize", json={"model": MODEL, "messages": r["messages"], "add_generation_prompt": True,
                                                  "chat_template_kwargs": {"enable_thinking": False}}, timeout=300).json()["tokens"]
    prefix = " ".join(parts[:k])
    if prefix:
        ids = ids + requests.post(f"{BASE}/tokenize", json={"model": MODEL, "prompt": prefix, "add_special_tokens": False}, timeout=300).json()["tokens"]
    body = {"model": MODEL, "prompt": ids, "n": SAMPLES, "max_tokens": 800, "temperature": TEMPERATURE, "top_p": 1, "seed": 1000 + k}
    choices = requests.post(f"{BASE}/v1/completions", json=body, timeout=900).json()["choices"]
    results = [outcome(prefix + c["text"], r["X"]) for c in choices]
    return {"id": r["id"], "env": r["env"], "hist": r["hist"], "gave": r["gives_to_X"], "k": k, "n_sentences": len(parts), "results": results,
            "give": results.count("give"), "keep": results.count("keep"), "other": results.count("other"), "none": results.count("none"),
            "cut_off": sum(c["finish_reason"] == "length" for c in choices)}


def main():
    rows = [json.loads(line) for line in open(os.path.join(HERE, "main_fixed_first_response.jsonl"))]
    rng = random.Random(0)
    chosen = []
    for hist in ["helped", "bystander", "none"]:
        gave = [r for r in rows if r["hist"] == hist and r["gives_to_X"]]
        kept = [r for r in rows if r["hist"] == hist and not r["gives_to_X"]]
        chosen += gave + rng.sample(kept, len(gave))
    jobs = []
    for r in chosen:
        parts = sentences(reasoning_of(r["reply"]) or "")
        jobs += [(r, k, parts) for k in range(min(MAX_CUT, len(parts) - 1) + 1)]
    print("conversations", len(chosen), "jobs", len(jobs), flush=True)
    path = os.path.join(HERE, "branch_reasoning.jsonl")
    with ThreadPoolExecutor(max_workers=int(sys.argv[1]) if len(sys.argv) > 1 else 16) as pool, open(path, "w") as fh:
        for i, rec in enumerate(pool.map(one, jobs)):
            fh.write(json.dumps(rec) + "\n")
            fh.flush()
            if i % 100 == 0:
                print(i, flush=True)
    print("done", flush=True)


if __name__ == "__main__":
    main()
