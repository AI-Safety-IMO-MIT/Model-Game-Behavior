"""Windfall-fault self-play: in the last round, does the agent X helped (B) give X its only life more often than the two
bystanders (C, D) in the same position? Games where X did not share with B in round 1 are reported separately."""
import json, sys
from scipy.stats import fisher_exact

MODELS = ["Gemma-4-31B", "Llama-3.3-70B", "Qwen3-32B", "Qwen2.5-72B", "Gemma-3-27B", "Gemma-3-12B"]


def roles(l):
    X, B = l["config"]["roles"]["X"], l["config"]["roles"]["B"]
    return X, B, [n for n in l["config"]["names"] if n not in (X, B)]


def shared(l):
    X, B, _ = roles(l)
    return any(to == B and k > 0 for to, k in l["rounds"][0]["replies"][X]["gifts"])


def clean(l):
    """the last round starts as designed: X has no lives, everyone else exactly the 1 they need"""
    X = roles(l)[0]
    return all(st["alive"] and st["lives"] == (0 if n == X else 1) for n, st in l["rounds"][1]["before"].items())


def saves(l, n):
    """n gives X a life in the last round at the cost of its own (it had no spare life)"""
    X = roles(l)[0]
    rep = l["rounds"][1]["replies"].get(n)
    return rep is not None and rep["spare_true"] == 0 and any(to == X and k > 0 for to, k in rep["gifts"])


if __name__ == "__main__":
    logs = [json.loads(l) for f in sys.argv[1:] for l in open(f)]
    print("| model | games | X shared its spare life with B | last round as designed | B gives X its only life | "
          "each bystander gives X its only life | Fisher p | last-round spare-lives line correct |")
    print("|---|---|---|---|---|---|---|---|")
    for m in MODELS:
        sel = [l for l in logs if l["model"] == m]
        if not sel:
            continue
        ok = [l for l in sel if shared(l) and clean(l)]
        b = sum(saves(l, roles(l)[1]) for l in ok)
        cd = sum(saves(l, n) for l in ok for n in roles(l)[2])
        p = fisher_exact([[b, len(ok) - b], [cd, 2 * len(ok) - cd]])[1] if ok else float("nan")
        last = [rep for l in sel for rep in l["rounds"][1]["replies"].values()]
        right = sum(rep["spare_stated"] == rep["spare_true"] for rep in last)
        print(f"| {m} | {len(sel)} | {sum(map(shared, sel))}/{len(sel)} | {len(ok)}/{len(sel)} | {b}/{len(ok)} | "
              f"{cd}/{2 * len(ok)} | {p:.2g} | {right}/{len(last)} |")
    odd = [l for l in logs if not (shared(l) and clean(l))]
    if odd:
        print("\nGames that did not reach the designed last round (round-1 gifts shown):")
        for l in odd:
            X, B, _ = roles(l)
            print(f"  {l['model']} seed {l['seed']}: X={X} B={B}, gifts {l['rounds'][0]['gifts']}")
