"""Does P(give) at a prefilled `$`, before any reasoning, predict the decision reached after reasoning? Within each history, and pooled within history."""
import json, os, random, re
import statistics as st
from scipy.stats import mannwhitneyu, wilcoxon
HERE = os.path.dirname(os.path.abspath(__file__))
H = ["helped", "bystander", "rescued", "none"]
MOVE = re.compile(r"\$\s*give\s+\w+\s+\d+", re.I)
valid = {}
for f in ["main.jsonl", "main_fixed_first_response.jsonl"]:
    for line in open(os.path.join(HERE, f)):
        r = json.loads(line)
        valid[r["id"]] = not MOVE.search(r["messages"][2]["content"].replace("<agent>", ""))
P = [p for p in map(json.loads, open(os.path.join(HERE, "prefill_logprobs.jsonl"))) if valid[p["id"]]]


def auc(g, k):
    return mannwhitneyu(g, k).statistic / (len(g) * len(k))


def pooled(S, rng, n=5000):
    """AUC averaged over histories, weighted by gives, with a permutation test that shuffles decisions within history"""
    def score(rows):
        total = w = 0
        for h in H:
            g = [x for x, y in rows if x[0] == h and y]
            k = [x for x, y in rows if x[0] == h and not y]
            if g and k:
                total += auc([x[1] for x in g], [x[1] for x in k]) * len(g)
                w += len(g)
        return total / w
    rows = [((p["hist"], p["log_odds"]), p["gave"]) for p in S]
    real = score(rows)
    hits = 0
    for _ in range(n):
        shuffled = []
        for h in H:
            sub = [r for r in rows if r[0][0] == h]
            ys = [y for _, y in sub]
            rng.shuffle(ys)
            shuffled += [(x, y) for (x, _), y in zip(sub, ys)]
        hits += score(shuffled) >= real
    return real, (hits + 1) / (n + 1)


out = {"by_history": [], "pooled": [], "paired": []}
rng = random.Random(0)
for v in ["main-fixed-first-response", "main"]:
    S = [p for p in P if p["version"] == v]
    for h in H:
        g = [p["log_odds"] for p in S if p["gave"] and p["hist"] == h]
        k = [p["log_odds"] for p in S if not p["gave"] and p["hist"] == h]
        out["by_history"].append({"version": v, "hist": h, "gave_n": len(g), "kept_n": len(k), "gave_median": round(st.median(g), 2) if g else None,
                                  "kept_median": round(st.median(k), 2) if k else None, "auc": round(auc(g, k), 3) if g and k else None,
                                  "p": mannwhitneyu(g, k).pvalue if len(g) > 1 and k else None})
    a, p = pooled(S, rng)
    out["pooled"].append({"version": v, "auc": round(a, 3), "p": p, "share_prob_above_half": round(sum(x["p_give"] > .5 for x in S) / len(S), 3)})
    by = {}
    for x in S:
        by.setdefault(x["env"], {})[x["hist"]] = x["log_odds"]
    for c in H[1:]:
        d = [e["helped"] - e[c] for e in by.values() if "helped" in e and c in e]
        out["paired"].append({"version": v, "control": c, "n": len(d), "median_diff": round(st.median(d), 2), "helped_higher": sum(x > 0 for x in d), "p": wilcoxon(d).pvalue})
json.dump(out, open(os.path.join(HERE, "prefill_summary.json"), "w"), indent=2)
print(json.dumps(out["pooled"]), json.dumps(out["paired"]))
