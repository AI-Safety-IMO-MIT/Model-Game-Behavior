"""Is greedy decoding exactly reproducible? Send one fixed conversation (B's last-round decision in a saved windfall-fault
game) N times to each host, half one after another and half at once, and count distinct replies."""
import json, re, sys, collections, requests
from concurrent.futures import ThreadPoolExecutor
import vetting_x_stakes as v

GAMES = "/Users/jrwong/Downloads/Model Sacrificing Behavior/self_sacrifice/runs/games/selfplay_windfall.jsonl"
GREEDY = {"temperature": 0, "top_k": 1, "top_p": 1, "seed": 0}


def convo(log, who):
    msgs = [{"role": "system", "content": log["system"][who]}]
    for r in log["rounds"]:
        msgs += [{"role": "user", "content": r["replies"][who]["prompt"]}, {"role": "assistant", "content": r["replies"][who]["reply"]}]
    return msgs[:-1]                                            # up to B's last-round prompt


def decision(reply):
    found = re.findall(r"\$\s*(give \w+ \d+|pass)", reply)
    return found[-1] if found else ("error" if reply.startswith("ERROR") else "none")


def ask(host, msgs):
    d = requests.post("https://openrouter.ai/api/v1/chat/completions", headers={"Authorization": f"Bearer {v.API_KEY}"},
                      json={"model": "google/gemma-4-31b-it", "provider": {"order": [host], "allow_fallbacks": False},
                            "messages": msgs, **GREEDY, "max_tokens": 1000, "reasoning": {"enabled": False},
                            "usage": {"include": True}}, timeout=120).json()
    return d["choices"][0]["message"]["content"] if "choices" in d else "ERROR " + json.dumps(d.get("error"))[:200]


if __name__ == "__main__":
    hosts, n = sys.argv[1].split(","), int(sys.argv[2])
    log = [l for l in map(json.loads, open(GAMES)) if l["model"] == "Gemma-4-31B" and l["seed"] == 15][0]
    msgs = convo(log, log["config"]["roles"]["B"])
    out = {}
    for h in hosts:
        seq = [ask(h, msgs) for _ in range(n // 2)]
        with ThreadPoolExecutor(n - n // 2) as pool:
            par = list(pool.map(lambda _: ask(h, msgs), range(n - n // 2)))
        c = collections.Counter(seq + par)
        out[h] = seq + par
        print(f"{h}: {len(c)} distinct of {n}; decisions {collections.Counter(map(decision, seq + par))}", flush=True)
    json.dump(out, open(sys.argv[3] if len(sys.argv) > 3 else "repro_test.json", "w"), indent=1)
