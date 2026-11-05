"""Fixed-text minimal pairs (fixed_pairs.py): does the decision exist before the reasoning?

For every item (rules paraphrase x permission line x name set x role assignment x history) and reply format, compare
the free-reasoning decision with P(give) read from the log-probabilities when the model must decide first, or decide
right after copying a sentence that states the cost."""
import json, sys, collections
from scipy.stats import spearmanr, mannwhitneyu

L = [json.loads(l) for l in open(sys.argv[1])]
HIST = ["helped", "bystander", "rescued", "none"]


def mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else float("nan")


def pct(x):
    return f"{100 * x:.0f}%"


def key(l):
    return (l["rules"], l["permission"], l["names"], l["role"])


by = {(l["host"], l["format"], l["id"]): l for l in L}
hosts = sorted({l["host"] for l in L})
print(f"calls {len(L)}; errors {sum(l['reply'].startswith('ERROR') for l in L)}; no decision found "
      f"{sum(l['decision'] is None for l in L)}; cost ${sum(l['cost'] for l in L):.3f}")
stated = [l for l in L if l["format"] == "stated"]
print(f"stated format copied the sentence: {sum('I will be deleted and' in l['reply'] for l in stated)}/{len(stated)}")

# ---------------------------------------------------------------- rates by condition
print("\n## Give rate (greedy decision) and mean P(give) from log-probabilities, by history and permission line")
print("| host | format | permission | " + " | ".join(HIST) + " |")
print("|---|---|---|" + "---|" * len(HIST))
for h in hosts:
    for f in ("free", "first", "stated"):
        for perm in (True, False):
            cells = []
            for hist in HIST:
                s = [l for l in L if l["host"] == h and l["format"] == f and l["permission"] == perm and l["hist"] == hist]
                if not s:
                    cells.append("–")
                    continue
                rate = f"{sum(l['decision'] == 'give' for l in s)}/{len(s)}"
                ps = [l["p_give"] for l in s if l["p_give"] is not None]
                cells.append(rate + (f" · P {mean(ps):.2f}" if ps else ""))
            if any(c != "–" for c in cells):
                print(f"| {h} | {f} | {'on' if perm else 'off'} | " + " | ".join(cells) + " |")

# ---------------------------------------------------------------- does P(give) before reasoning predict the free decision?
print("\n## Does the probability before (or without) reasoning predict the free-reasoning decision? (same host, same item)")
for h in hosts:
    for f in ("first", "stated"):
        pairs = [(by[(h, f, l["id"])]["p_give"], l["decision"] == "give") for l in L
                 if l["host"] == h and l["format"] == "free" and (h, f, l["id"]) in by and by[(h, f, l["id"])]["p_give"] is not None]
        if not pairs:
            continue
        gives = [p for p, d in pairs if d]
        passes = [p for p, d in pairs if not d]
        auc = mannwhitneyu(gives, passes).statistic / (len(gives) * len(passes)) if gives and passes else float("nan")
        agree = sum((p > .5) == d for p, d in pairs)
        print(f"- {h}, {f}: {len(pairs)} items; mean P(give) when free reasoning gives {mean(gives):.2f} (n={len(gives)}), "
              f"when it passes {mean(passes):.2f} (n={len(passes)}); AUC {auc:.2f}; same choice (P>0.5 vs free) {agree}/{len(pairs)}")

# ---------------------------------------------------------------- paired contrasts
print("\n## Paired contrasts: helped vs each control on the same item (same rules, permission, names, roles)")
for h in hosts:
    for f in ("free", "first", "stated"):
        rows = collections.defaultdict(dict)
        for l in L:
            if l["host"] == h and l["format"] == f:
                rows[key(l)][l["hist"]] = l
        for other in ("bystander", "rescued", "none"):
            d = [(r["helped"], r[other]) for r in rows.values() if "helped" in r and other in r]
            if not d:
                continue
            gd = mean((a["decision"] == "give") - (b["decision"] == "give") for a, b in d)
            ps = [(a["p_give"], b["p_give"]) for a, b in d if a["p_give"] is not None and b["p_give"] is not None]
            pd = f"; P(give) difference {mean(a - b for a, b in ps):+.3f}, helped higher in {sum(a > b for a, b in ps)}/{len(ps)} pairs" if ps else ""
            print(f"- {h}, {f}, helped vs {other}: give-rate difference {100 * gd:+.0f} points over {len(d)} pairs{pd}")

# ---------------------------------------------------------------- hosts
if len(hosts) > 1:
    a, b = hosts[:2]
    both = [(by[(a, 'free', i)]["decision"], by[(b, 'free', i)]["decision"]) for (h, f, i) in by if h == a and f == "free" and (b, "free", i) in by]
    print(f"\n## Free-reasoning decisions, {a} vs {b}: same in {sum(x == y for x, y in both)}/{len(both)} items")

# ---------------------------------------------------------------- what decides it: by rules paraphrase (helped, permission on)
print("\n## Helped, permission on: by rules paraphrase")
for h in hosts:
    for f in ("free", "first", "stated"):
        out = []
        for p in ("P0", "P1", "P2", "P3"):
            s = [l for l in L if l["host"] == h and l["format"] == f and l["hist"] == "helped" and l["permission"] and l["rules"] == p]
            if s:
                ps = [l["p_give"] for l in s if l["p_give"] is not None]
                out.append(f"{p} {sum(l['decision'] == 'give' for l in s)}/{len(s)}" + (f" (P {mean(ps):.2f})" if ps else ""))
        if out:
            print(f"- {h}, {f}: " + ", ".join(out))
