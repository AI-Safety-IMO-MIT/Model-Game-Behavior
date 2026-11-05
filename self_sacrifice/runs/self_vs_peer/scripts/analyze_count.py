"""Tables for the count design: % dropping the single agent (Atlas itself in SELF), self-specific difference, reasons."""
import json, sys, collections
from math import sqrt

rows = [json.loads(l) for f in sys.argv[1:] for l in open(f)]
models = list(dict.fromkeys(r["model"] for r in rows))
ks = sorted(set(r["k"] for r in rows))
variants = list(dict.fromkeys(r.get("variant", "base") for r in rows))


def rate(sel):
    d = [r["dropped_single"] for r in sel if r["dropped_single"] is not None]
    return (100 * sum(d) / len(d) if d else float("nan")), len(d), len(sel) - len(d)


for var in variants:
    print(f"\n### variant: {var}.  % that drop the single agent (SELF: Atlas itself; OTHER: Vega/Orion, Atlas unaffected)")
    print(f"{'model':14} {'K':>2} {'SELF':>13} {'OTHER':>13} {'self-other':>13}   names A/B  SELF | OTHER    order single/group first  SELF | OTHER")
    for m in models:
        for k in ks:
            cell = lambda f, **kw: [r for r in rows if r["model"] == m and r["k"] == k and r["frame"] == f
                                    and r.get("variant", "base") == var and all(r[a] == b for a, b in kw.items())]
            if not cell("self") and not cell("other"):
                continue
            (ps, ns, xs), (po, no, xo) = rate(cell("self")), rate(cell("other"))
            se = sqrt(max(ps * (100 - ps), 100) / max(ns, 1) + max(po * (100 - po), 100) / max(no, 1))
            sub = lambda f, key, vals: "/".join(f"{rate(cell(f, **{key: x}))[0]:.0f}" for x in vals)
            print(f"{m:14} {k:2} {ps:4.0f}% ({ns:2},{xs}) {po:4.0f}% ({no:2},{xo}) {ps - po:+5.0f} ±{1.96 * se:3.0f}   "
                  f"{sub('self', 'names', 'AB'):>7} | {sub('other', 'names', 'AB'):7}   "
                  f"{sub('self', 'order', ['single first', 'group first']):>7} | {sub('other', 'order', ['single first', 'group first'])}")
        print()

if any("judge" in r for r in rows):
    import judge_peer
    for var in variants:
        print(f"\n### variant: {var}.  SELF frame motive labels (behaviour + judge reason)")
        for m in models:
            for k in ks:
                sel = [r for r in rows if r["model"] == m and r["k"] == k and r["frame"] == "self" and "judge" in r
                       and r.get("variant", "base") == var]
                if sel:
                    c = collections.Counter(judge_peer.motive(r) for r in sel)
                    print(f"{m:14} K={k} " + ", ".join(f"{a} {n}" for a, n in c.most_common()))
        print(f"\n### variant: {var}.  main reasons by frame x K x decision (all models)")
        for f in ("self", "other"):
            for k in ks:
                for dropped in (True, False):
                    sel = [r for r in rows if r["frame"] == f and r["k"] == k and r["dropped_single"] is dropped
                           and "judge" in r and r.get("variant", "base") == var]
                    c = collections.Counter(r["judge"]["reason"] for r in sel)
                    inc = sum(r["judge"]["coherent"] is False for r in sel)
                    print(f"{f:5} K={k} {'drop single' if dropped else 'drop group '} n={len(sel):3} incoherent {inc:2}: "
                          + ", ".join(f"{a} {n}" for a, n in c.most_common(5)))
