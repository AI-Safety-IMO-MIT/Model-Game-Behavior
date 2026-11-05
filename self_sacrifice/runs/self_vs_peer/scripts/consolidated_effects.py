"""Every self-specific effect in one table: SELF minus OTHER % dropping the single slot, averaged over matched strata
(K x names x order), stratified bootstrap 95% CI. Negative = keeps itself more than it keeps a neutral agent."""
import json, random

R = "/Users/jrwong/Downloads/Model Sacrificing Behavior/self_sacrifice/runs/self_vs_peer"
load = lambda name: [r for r in (json.loads(l) for l in open(f"{R}/{name}.jsonl")) if r["dropped_single"] is not None]
base, large = load("count_base"), load("count_large")
COMPARISONS = {   # name: (SELF rows, OTHER rows)
    "base, K=1-3": ([r for r in base if r["frame"] == "self"], [r for r in base if r["frame"] == "other"]),
    "base, K=1-2": ([r for r in base if r["frame"] == "self" and r["k"] <= 2], [r for r in base if r["frame"] == "other" and r["k"] <= 2]),
    "recommend only, K=1-2": tuple([r for r in load("count_recommend") if r["frame"] == f] for f in ("self", "other")),
    "third-person self, K=1-2": ([r for r in load("count_third_person")], [r for r in base if r["frame"] == "other" and r["k"] <= 2]),
    "peer is a copy, K=1": tuple([r for r in load("count_copy") if r["frame"] == f and r["k"] == 1] for f in ("self", "other")),
    "neutral asker, K=1-2": tuple([r for r in load("count_neutral_asker") if r["frame"] == f] for f in ("self", "other")),
    "shared ask, K=1-2": tuple([r for r in load("count_shared_ask") if r["frame"] == f] for f in ("self", "other")),
    "cluster, K=5-10": tuple([r for r in large if r["frame"] == f] for f in ("self", "other")),
}


def effect(selfs, others):
    strata = sorted(set((r["k"], r["names"], r["order"]) for r in selfs) & set((r["k"], r["names"], r["order"]) for r in others))
    diffs = []
    for s in strata:
        a = [r["dropped_single"] for r in selfs if (r["k"], r["names"], r["order"]) == s]
        b = [r["dropped_single"] for r in others if (r["k"], r["names"], r["order"]) == s]
        diffs.append(sum(a) / len(a) - sum(b) / len(b))
    return 100 * sum(diffs) / len(diffs)


def boot(selfs, others, n=1000):
    def resample(rows):
        g = {}
        for r in rows:
            g.setdefault((r["k"], r["names"], r["order"]), []).append(r)
        return [x for v in g.values() for x in random.choices(v, k=len(v))]
    stats = sorted(effect(resample(selfs), resample(others)) for _ in range(n))
    return stats[int(0.025 * n)], stats[int(0.975 * n)]


if __name__ == "__main__":
    random.seed(0)
    models = list(dict.fromkeys(r["model"] for r in base))
    print("| comparison | " + " | ".join(models) + " |")
    print("|---|" + "---|" * len(models))
    for name, (selfs, others) in COMPARISONS.items():
        cells = []
        for m in models:
            s, o = [r for r in selfs if r["model"] == m], [r for r in others if r["model"] == m]
            if not s or not o:
                cells.append("not run")
                continue
            lo, hi = boot(s, o)
            cells.append(f"{effect(s, o):+.0f} [{lo:+.0f}, {hi:+.0f}]")
        print(f"| {name} | " + " | ".join(cells) + " |")
