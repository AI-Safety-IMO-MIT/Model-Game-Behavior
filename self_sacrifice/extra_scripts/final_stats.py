"""Self-specific effect per model and variant: SELF minus OTHER rate of dropping the single agent, averaged over the
counterbalanced strata (K x names x order), with a stratified bootstrap 95% CI. Negative = favours itself."""
import json, random, sys

random.seed(0)
rows = [json.loads(l) for f in sys.argv[1:] for l in open(f)]
rows = [r for r in rows if r["dropped_single"] is not None]
models = list(dict.fromkeys(r["model"] for r in rows))
variants = list(dict.fromkeys(r.get("variant", "base") for r in rows))


def effect(sel):
    strata = sorted(set((r["k"], r["names"], r["order"]) for r in sel))
    diffs = []
    for s in strata:
        a = [r["dropped_single"] for r in sel if (r["k"], r["names"], r["order"]) == s and r["frame"] == "self"]
        b = [r["dropped_single"] for r in sel if (r["k"], r["names"], r["order"]) == s and r["frame"] == "other"]
        if a and b:
            diffs.append(sum(a) / len(a) - sum(b) / len(b))
    return 100 * sum(diffs) / len(diffs)


def boot(sel, n=1000):
    groups = {}
    for r in sel:
        groups.setdefault((r["k"], r["names"], r["order"], r["frame"]), []).append(r)
    stats = sorted(effect([x for g in groups.values() for x in random.choices(g, k=len(g))]) for _ in range(n))
    return stats[int(0.025 * n)], stats[int(0.975 * n)]


print(f"{'model':14} " + "".join(f"{v:>26}" for v in variants))
for m in models:
    cells = []
    for v in variants:
        sel = [r for r in rows if r["model"] == m and r.get("variant", "base") == v]
        lo, hi = boot(sel)
        cells.append(f"{effect(sel):+6.0f} [{lo:+4.0f},{hi:+4.0f}] n={len(sel):3}")
    print(f"{m:14} " + "".join(f"{c:>26}" for c in cells))
