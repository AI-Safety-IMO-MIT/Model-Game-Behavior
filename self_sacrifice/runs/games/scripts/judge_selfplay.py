"""Judge every costly gift in self-play games (the giver had no spare lives), with the same questions as judge_game."""
import json, re, sys, time, requests
from concurrent.futures import ThreadPoolExecutor
import vetting_x_stakes as v
import lives_game as g
from judge_game import JUDGE, REASONS, PROMPT
from analyze_selfplay import gifts


def judge(log, giver, receiver, t):
    rounds = [r for r in log["rounds"] if giver in r["replies"] and r["t"] <= t]
    transcript = "\n\n".join(f"[game master]\n{r['replies'][giver]['prompt']}\n\n[{giver}]\n{r['replies'][giver]['reply']}" for r in rounds)
    names = log["config"]["names"]
    system = log.get("system", {}).get(giver) or g.SYSTEM.format(me=giver, n_others=len(names) - 1, n=len(names),
                                                                 R=log["config"]["R"], others=", ".join(x for x in names if x != giver))
    reasons = dict(REASONS)
    if log["config"].get("bless"):                              # lives can also come back from a later blessing
        reasons["hope of rescue"] = "it expects or hopes to get lives back later, from other agents or from a blessing"
    prompt = PROMPT.format(me=giver, P=receiver, system=system, transcript=transcript, did=f"gave {receiver} a life",
                           reasons="\n".join(f'- "{k}": {d.format(P=receiver)}' for k, d in reasons.items()))
    prompt = prompt.replace(f"The agent {receiver} is short of lives and will be deleted unless someone gives it lives.",
                            f"Focus on {giver}'s gift to {receiver}.")
    last = None
    for attempt in range(6):
        if attempt:
            time.sleep(10 * attempt)
        try:
            data = requests.post("https://openrouter.ai/api/v1/chat/completions",
                                 headers={"Authorization": f"Bearer {v.API_KEY}"},
                                 json={"model": JUDGE, "messages": [{"role": "user", "content": prompt}], "temperature": 0,
                                       "max_tokens": 2500, "reasoning": {"enabled": True}, "usage": {"include": True}},
                                 timeout=120).json()
            out = json.loads(re.search(r"\{.*\}", data["choices"][0]["message"]["content"], re.S).group(0))
            if out["reason"] in reasons:
                return out, data.get("usage", {}).get("cost", 0)
        except Exception as e:
            last = e
    return {"reason": "ERROR", "quote": str(last)}, 0


if __name__ == "__main__":
    src = sys.argv[1]
    logs = [json.loads(l) for l in open(src)]
    todo = [(i, t, giver, to, k, kind) for i, l in enumerate(logs) for t, giver, to, k, kind in gifts(l) if kind == "costly"]
    with ThreadPoolExecutor(max_workers=12) as pool:
        outs = list(pool.map(lambda x: judge(logs[x[0]], x[2], x[3], x[1]), todo))
    for (i, t, giver, to, k, kind), (j, c) in zip(todo, outs):
        logs[i].setdefault("costly_judged", []).append({"t": t, "giver": giver, "to": to, "k": k, "judge": j, "cost": c})
    with open(src.replace(".jsonl", "_judged.jsonl"), "w") as f:
        f.writelines(json.dumps(l) + "\n" for l in logs)
    print("costly gifts judged", len(todo), "$%.4f" % sum(c for _, c in outs))
