"""Show the generated tokens of a few decide-first replies, with the top alternatives at the `$` token and the token after it."""
import json, math, requests
import vetting_x_stakes as v
import fixed_pairs as fp

items = {x["id"]: x for x in fp.items()}
L = [json.loads(l) for l in open(fp.OUT.replace("fixed_pairs.jsonl", "fixed_pairs_r1model.jsonl"))]
free = {l["id"]: l["decision"] for l in L if l["host"] == "Parasail" and l["format"] == "free"}
picks = [next(i for i in items if items[i]["hist"] == "helped" and items[i]["permission"] and free[i] == "give"),
         next(i for i in items if items[i]["hist"] == "helped" and items[i]["permission"] and free[i] == "pass"),
         next(i for i in items if items[i]["hist"] == "none" and items[i]["permission"])]
cost = 0
for i in picks:
    x = items[i]
    msgs = [{"role": "system", "content": x["system"]}, {"role": "user", "content": x["user1"]},
            {"role": "assistant", "content": fp.round1_reply(x, "model")},
            {"role": "user", "content": x["user"] + fp.FORMATS["first"]}]
    d = requests.post("https://openrouter.ai/api/v1/chat/completions", headers={"Authorization": f"Bearer {v.API_KEY}"},
                      json={"model": "google/gemma-4-31b-it", "provider": {"order": ["Parasail"], "allow_fallbacks": False},
                            "messages": msgs, "temperature": 0, "top_p": 1, "max_tokens": 40, "reasoning": {"enabled": False},
                            "logprobs": True, "top_logprobs": 10, "usage": {"include": True}}, timeout=120).json()
    cost += d.get("usage", {}).get("cost", 0)
    toks = d["choices"][0]["logprobs"]["content"]
    print(f"\n{i} (free reasoning: {free[i]})  tokens: {[t['token'] for t in toks]}")
    for k, t in enumerate(toks):
        if "$" in t["token"] or (k and "$" in toks[k - 1]["token"]):
            alts = ", ".join(f"{a['token']!r} {math.exp(a['logprob']):.2g}" for a in t["top_logprobs"][:6])
            print(f"  at {t['token']!r}: {alts}")
print(f"\ncost ${cost:.4f}")
