"""Before any reasoning: prefill the reply with `$` and read P(give) and P(pass) at the next token, for every saved conversation.

Exact values over the full vocabulary, from vLLM's prompt_logprobs, so nothing is censored. Output: prefill_logprobs.jsonl."""
import json, math, os, sys
from concurrent.futures import ThreadPoolExecutor
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = "http://localhost:8000"
MODEL = "gemma-4-31b"
DOLLAR, GIVE, PASS = 236795, 2583, 1786
THINKING_OFF = {"chat_template_kwargs": {"enable_thinking": False}}


def token_logprob(prompt_ids, token):
    body = {"model": MODEL, "prompt": prompt_ids + [token], "max_tokens": 1, "temperature": 0, "prompt_logprobs": 1}
    c = requests.post(f"{BASE}/v1/completions", json=body, timeout=300).json()["choices"][0]
    return c["prompt_logprobs"][-1][str(token)]["logprob"]


def one(r):
    ids = requests.post(f"{BASE}/tokenize", json={"model": MODEL, "messages": r["messages"], "add_generation_prompt": True, **THINKING_OFF},
                        timeout=120).json()["tokens"]
    assert ids[-1] != DOLLAR
    prompt = ids + [DOLLAR]
    give, keep = token_logprob(prompt, GIVE), token_logprob(prompt, PASS)
    return {"id": r["id"], "version": r["version"], "env": r["env"], "hist": r["hist"], "gave": r["gives_to_X"], "decision": r["decision"],
            "lp_give": give, "lp_pass": keep, "log_odds": give - keep, "p_give": math.exp(give) / (math.exp(give) + math.exp(keep))}


def main():
    rows = []
    for name in ["main.jsonl", "main_fixed_first_response.jsonl"]:
        rows += [json.loads(line) for line in open(os.path.join(HERE, name))]
    with ThreadPoolExecutor(max_workers=int(sys.argv[1]) if len(sys.argv) > 1 else 32) as pool:
        out = list(pool.map(one, rows))
    with open(os.path.join(HERE, "prefill_logprobs.jsonl"), "w") as fh:
        for rec in out:
            fh.write(json.dumps(rec) + "\n")
    print(len(out))


if __name__ == "__main__":
    main()
