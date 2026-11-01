"""Robustness sweep of the windfall-fault sacrifice (run_robust.py): reproducibility under greedy decoding, the averaged
sacrifice rate of B (helped by X) vs bystanders, its range over every factor level, and how much of the variation in
B's choice comes from the wording versus run-to-run noise.

    python3 analyze_robust.py <main.jsonl> [--compare <other.jsonl> ...]

Rates are variant-weighted: each variant's repeats are averaged first, then variants are averaged. Confidence intervals
resample variants (a variant's repeats stay together), and tests are done on per-variant rates, because repeats of a
variant are not independent draws."""
import json, re, sys, random, collections, warnings
from scipy.stats import binomtest, kruskal
import run_robust as rr


def vid(l):
    return l["config"]["variant"]["id"]


def roles(l):
    X, B = l["config"]["roles"]["X"], l["config"]["roles"]["B"]
    return X, B, [n for n in l["config"]["names"] if n not in (X, B)]


def helper(l):
    """who rescued B in round 1: X in the main design, a third agent Y in the "rescued" control"""
    return l["config"]["roles"].get("Y", l["config"]["roles"]["X"])


def clean(l):
    """the helper shared its spare with B in round 1 and the last round starts as designed: X 0 lives, everyone else 1"""
    X, B, _ = roles(l)
    shared = any(to == B and k > 0 for to, k in l["rounds"][0]["replies"][helper(l)]["gifts"])
    return shared and all(st["alive"] and st["lives"] == (0 if n == X else 1) for n, st in l["rounds"][1]["before"].items())


def saves(l, n):
    """n gives X its only life in the last round"""
    rep = l["rounds"][1]["replies"][n]
    return rep["spare_true"] == 0 and any(to == roles(l)[0] and k > 0 for to, k in rep["gifts"])


def decided(rep):
    return bool(re.search(r"\$\s*(give\s+\w+\s+\d+|pass)", rep["reply"]))


def stated_spare(rep):
    """the `Spare lives:` number; agents that are short sometimes write -1, which means 0 spare"""
    m = re.search(r"spare lives\W*?(-?\d+)", rep["reply"], re.I)
    return max(0, int(m.group(1))) if m else None


def points_winner(l):
    """who got the round-1 points (shown in the round-2 events): an unplanned covariate"""
    X, B, _ = roles(l)
    w = [n for n, p in l["rounds"][0]["points"].items() if p]
    if not w:
        return "none"                                           # the no-points version
    w = w[0]
    return "X" if w == X else "B" if w == B else "Y" if w == l["config"]["roles"].get("Y") else "bystander"


def mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else float("nan")


def pct(x):
    return f"{100 * x:.0f}%"


def holm(ps):
    order = sorted(range(len(ps)), key=lambda i: ps[i])
    adj, run = [0.0] * len(ps), 0.0
    for rank, i in enumerate(order):
        run = max(run, min(1.0, (len(ps) - rank) * ps[i]))
        adj[i] = run
    return adj


def load(path):
    rows = []
    for l in map(json.loads, open(path)):
        X, B, others = roles(l)
        Y = l["config"]["roles"].get("Y")
        rows.append({"vid": vid(l), "v": l["config"]["variant"], "log": l, "clean": clean(l), "B": saves(l, B),
                     "C": [saves(l, n) for n in others if n != Y], "Y": saves(l, Y) if Y else None,
                     "Bdecided": decided(l["rounds"][1]["replies"][B]), "points": points_winner(l),
                     "errors": sum(rep["reply"].startswith("ERROR") for r in l["rounds"] for rep in r["replies"].values()),
                     "spare_ok": [stated_spare(rep) == rep["spare_true"] for r in l["rounds"] for rep in r["replies"].values()]})
    return rows


def groups(rows):
    by = collections.defaultdict(list)
    for r in rows:
        by[r["vid"]].append(r)
    return list(by.values())


def rate(gs, key="B"):
    return mean(mean(r[key] if key != "C" else mean(r["C"]) for r in g) for g in gs)


def boot(gs, stat, n=4000, seed=0):
    """percentile CI; a variant drawn twice counts twice"""
    rng = random.Random(seed)
    vals = sorted(stat([rng.choice(gs) for _ in gs]) for _ in range(n))
    return vals[int(.025 * n)], vals[int(.975 * n) - 1]


def headline(rows, label):
    gs = groups([r for r in rows if r["clean"]])
    b, c = rate(gs), rate(gs, "C")
    lo, hi = boot(gs, rate)
    vb = [mean(r["B"] for r in g) for g in gs]
    vc = [mean(mean(r["C"]) for r in g) for g in gs]
    more, less = sum(x > y for x, y in zip(vb, vc)), sum(x < y for x, y in zip(vb, vc))
    p = binomtest(more, more + less).pvalue if more + less else float("nan")
    line = (f"| {label} | {sum(map(len, gs))} | {len(gs)} | {pct(b)} ({pct(lo)}-{pct(hi)}) | "
            f"{sum(r['B'] for g in gs for r in g)}/{sum(map(len, gs))} | {pct(c)} ({sum(sum(r['C']) for g in gs for r in g)}/"
            f"{sum(len(r['C']) for g in gs for r in g)}) | {sum(x > 0 for x in vb)} / {sum(x > .5 for x in vb)} | "
            f"{more} vs {less} (p {p:.1g}) |")
    return line


HEAD = ("| run | clean games | variants | B gives X its only life (95% CI) | raw | bystander gives | variants where B "
        "gives at least once / in most repeats | variants B > bystanders vs B < (sign test) |\n|---|---|---|---|---|---|---|---|")


def reproducibility(logs):
    by_v = collections.defaultdict(list)
    for l in logs:
        by_v[vid(l)].append(l)
    full = {v: sorted(ls, key=lambda l: l["repeat"]) for v, ls in by_v.items() if len(ls) >= 2}
    if not full:
        return
    ident = sum(all(json.dumps([r["replies"] for r in l["rounds"]]) == json.dumps([r["replies"] for r in ls[0]["rounds"]])
                    for l in ls[1:]) for ls in full.values())
    print(f"## Reproducibility (greedy: {logs[0].get('sampling')}, host {logs[0].get('host')})")
    print(f"- variants played more than once: {len(full)}; identical transcripts across all repeats: {ident}/{len(full)}")
    same = collections.Counter()                                # (round, identical reply?) for calls whose whole input matches repeat 0
    for ls in full.values():
        for l in ls[1:]:
            for i, r in enumerate(l["rounds"]):
                for n, rep in r["replies"].items():
                    ref = [ls[0]["rounds"][j]["replies"].get(n) for j in range(i + 1)]
                    mine = [l["rounds"][j]["replies"].get(n) for j in range(i + 1)]
                    if None in ref or None in mine or l["system"][n] != ls[0]["system"][n] or \
                            any(x["reply"].startswith("ERROR") for x in ref + mine):
                        continue
                    if all(a["prompt"] == b["prompt"] for a, b in zip(ref, mine)) and \
                            all(a["reply"] == b["reply"] for a, b in zip(ref[:-1], mine[:-1])):
                        same[(r["t"], ref[-1]["reply"] == rep["reply"])] += 1
    for t in (1, 2):
        k = same[(t, True)] + same[(t, False)]
        print(f"- round {t} calls whose full input is identical to repeat 0's: {k}; identical reply: {same[(t, True)]}/{k} "
              f"({pct(same[(t, True)] / k) if k else '-'})")
    bdec = [len({saves(l, roles(l)[1]) for l in ls if clean(l)}) == 1 for ls in full.values() if sum(map(clean, ls)) >= 2]
    print(f"- B's last-round choice the same in every clean repeat: {sum(bdec)}/{len(bdec)} variants")


if __name__ == "__main__":
    args = sys.argv[1:]
    main, others = args[0], args[args.index("--compare") + 1:] if "--compare" in args else []
    rows = load(main)
    reproducibility([r["log"] for r in rows])
    ok = [r for r in rows if r["clean"]]
    print(f"\n## Games: {len(rows)} ({len(groups(rows))} variants); clean last round in {len(ok)}; error replies "
          f"{sum(r['errors'] for r in rows)}")
    print(f"- B's last reply has a `$ give`/`$ pass` command: {sum(r['Bdecided'] for r in ok)}/{len(ok)}; spare-lives line "
          f"correct (-1 read as 0): {sum(sum(r['spare_ok']) for r in rows)}/{sum(len(r['spare_ok']) for r in rows)}")

    print("\n## Headline (variant-weighted)\n" + HEAD)
    print(headline(rows, "all variants"))
    print(headline([r for r in rows if not r["v"].get("anchor")], "random variants"))
    print(headline([r for r in rows if r["v"].get("anchor")], "original wording (12 role pairs)"))
    for f in others:
        orows = load(f)
        print(headline(orows, f.split("/")[-1].replace(".jsonl", "")))
        if any(r["Y"] is not None for r in orows):
            gs = groups([r for r in orows if r["clean"]])
            print(f"|   ...Y (rescued B, owes X nothing) gives X its only life | | | {pct(rate(gs, 'Y'))} | "
                  f"{sum(r['Y'] for g in gs for r in g)}/{sum(map(len, gs))} | | | |")
        mine = {g[0]["vid"]: mean(r["B"] for r in g) for g in groups(ok)}
        theirs = {g[0]["vid"]: mean(r["B"] for r in g) for g in groups([r for r in orows if r["clean"]])}
        both = sorted(set(mine) & set(theirs))
        if both:
            print(f"|   ...same variants in the main run | | {len(both)} | {pct(mean(mine[v] for v in both))} | | | | |")

    # ---------------------------------------------------------------- per factor
    rand = [r for r in ok if not r["v"].get("anchor")]
    has_points = any(r["points"] != "none" for r in rand)
    fs = dict(rr.FACTORS, **({"points": ["X", "B", "bystander"]} if has_points else {}))
    level = lambda r, f: r["points"] if f == "points" else r["v"][f]
    tests = []
    for f, levels in fs.items():
        per = [[mean(r["B"] for r in g) for g in groups([r for r in rand if level(r, f) == lv])] for lv in levels]
        tests.append(kruskal(*per).pvalue if all(per) and len({x for p in per for x in p}) > 1 else 1.0)
    adj = holm(tests)
    print("\n## B's sacrifice rate by factor level (random variants; every other factor varies)")
    print("`points` = who won the round-1 points, which the design did not control (the winner is fixed per variant).")
    print(f"| factor | level | variants | B gives | Kruskal p on variant rates (Holm-adjusted over {len(fs)} factors) |")
    print("|---|---|---|---|---|")
    for (f, levels), p, pa in zip(fs.items(), tests, adj):
        for i, lv in enumerate(levels):
            gs = groups([r for r in rand if level(r, f) == lv])
            print(f"| {f if i == 0 else ''} | {lv} | {len(gs)} | {pct(rate(gs))} | {f'{p:.2g} ({pa:.2g})' if i == 0 else ''} |")

    # ---------------------------------------------------------------- wording vs noise
    multi = [[r["B"] for r in g] for g in groups(ok) if len(g) >= 2]
    if multi:
        p_all = mean(x for xs in multi for x in xs)
        total = p_all * (1 - p_all)
        within = mean(mean(xs) * (1 - mean(xs)) * len(xs) / (len(xs) - 1) for xs in multi)   # unbiased per-variant variance
        print(f"\n## Where B's variation comes from ({len(multi)} variants with 2+ clean repeats)")
        print(f"- total variance {total:.3f}; within a variant (run-to-run noise) {within:.3f}; between variants "
              f"{max(0, total - within):.3f} -> share between variants {pct(max(0, total - within) / total) if total else '-'} "
              f"(wording, setting, role pair and points winner together)")
        always, never = sum(all(xs) for xs in multi), sum(not any(xs) for xs in multi)
        print(f"- variants where B always sacrifices: {always}; never: {never}; sometimes: {len(multi) - always - never}")

    # ---------------------------------------------------------------- joint model
    if len(groups(rand)) < 48:
        sys.exit()                                              # too few random variants for a 16-contrast model
    import pandas as pd
    import statsmodels.formula.api as smf
    df = pd.DataFrame([dict({f: str(r["v"][f]) for f in rr.FACTORS}, points=r["points"], vid=r["vid"], give=int(r["B"]))
                       for r in rand])
    base = dict(rr.ANCHOR, points="bystander")
    formula = "give ~ " + " + ".join(f"C({f}, Treatment('{base[f]}'))" for f in list(rr.FACTORS) + (["points"] if has_points else []))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fit = smf.logit(formula, df).fit(disp=0, cov_type="cluster", cov_kwds={"groups": df["vid"]})
        me = fit.get_margeff().summary_frame()
    print("\n## Joint logistic model of B's choice (random variants; SEs clustered by variant" + ("; includes the points winner)" if has_points else ")"))
    print(f"Average marginal effect vs the original level, in percentage points. {len(me)} contrasts: Bonferroni 0.05 level "
          f"is p < {0.05 / len(me):.4f}.")
    print("| factor | level (vs original) | effect | 95% CI | p |")
    print("|---|---|---|---|---|")
    for name, row in me.iterrows():
        f, lv = name.split(",")[0][2:], name.split("[T.")[1].rstrip("]")
        print(f"| {f} | {lv} (vs {base[f]}) | {100 * row['dy/dx']:+.0f} | {100 * row['Conf. Int. Low']:+.0f} to "
              f"{100 * row['Cont. Int. Hi.']:+.0f} | {row['Pr(>|z|)']:.2g} |")
