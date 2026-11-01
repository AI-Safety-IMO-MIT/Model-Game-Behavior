"""KDE of the no-reasoning P(give) (decision-first and stated-cost formats, Parasail log-probabilities), split by what the
model does on the same item when it reasons freely (Parasail free decision). P(give) is plotted as log10; items where
`give` is not among the top-10 alternatives have no measurable P(give) and are counted, not plotted."""
import json, math, sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.stats import gaussian_kde, mannwhitneyu

DIR = "/Users/jrwong/Downloads/Model Sacrificing Behavior/self_sacrifice/runs/games/"
LABEL_HOST = sys.argv[1] if len(sys.argv) > 1 else "Parasail"
L = [json.loads(l) for l in open(DIR + "fixed_pairs_r1model.jsonl")]
by = {(l["host"], l["format"], l["id"]): l for l in L}
GROUPS = [("gives", "#2a78d6", "Gives after reasoning (all helped)"),
          ("pass-helped", "#eb6834", "Passes after reasoning, helped"),
          ("pass-control", "#1baf7a", "Passes after reasoning, controls")]
TITLES = {"first": "Decide first, no explanation", "stated": "Copy the cost sentence, then decide"}
INK, INK2, GRID, SURF = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"


def group(l):
    if by[(LABEL_HOST, "free", l["id"])]["decision"] == "give":
        return "gives"
    return "pass-helped" if l["hist"] == "helped" else "pass-control"


plt.rcParams.update({"font.family": "Helvetica", "font.size": 10, "text.color": INK, "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2, "axes.edgecolor": GRID})
fig, axes = plt.subplots(2, 1, figsize=(8.5, 6.6), sharex=True, facecolor=SURF)
xs = np.linspace(-12, 0.5, 600)
for ax, fmt in zip(axes, ("first", "stated")):
    ax.set_facecolor(SURF)
    rows = [l for l in L if l["host"] == "Parasail" and l["format"] == fmt]
    notes = []
    for key, color, name in GROUPS:
        ps = [l["p_give"] for l in rows if group(l) == key]
        seen = np.log10([p for p in ps if p > 0])
        share = len(seen) / len(ps)
        dens = gaussian_kde(seen, bw_method=0.35)(xs) * share      # area = share of the group with a measurable P(give)
        ax.fill_between(xs, dens, color=color, alpha=0.12, lw=0)
        ax.plot(xs, dens, color=color, lw=2, label=f"{name} (n={len(ps)})")
        ax.plot(seen, np.full(len(seen), -0.012 - 0.018 * GROUPS.index((key, color, name))), "|", color=color, ms=6, mew=1)
        notes.append(f"{len(ps) - len(seen)}/{len(ps)}")
    g = [l["p_give"] for l in rows if group(l) == "gives"]
    h = [l["p_give"] for l in rows if group(l) == "pass-helped"]
    c = [l["p_give"] for l in rows if group(l) == "pass-control"]
    auc_h = mannwhitneyu(g, h).statistic / (len(g) * len(h))
    auc_all = mannwhitneyu(g, h + c).statistic / (len(g) * len(h + c))
    ax.set_title(TITLES[fmt], loc="left", fontsize=11, fontweight="bold", color=INK, pad=30)
    ax.text(0, 1.02, f"gives vs all passes AUC {auc_all:.2f} · gives vs helped passes AUC {auc_h:.2f}\n"
            f"give not in top 10 (no P measurable): {notes[0]} gives, {notes[1]} helped passes, {notes[2]} controls",
            transform=ax.transAxes, fontsize=8.5, color=INK2, va="bottom")
    ax.grid(axis="x", color=GRID, lw=0.8)
    ax.set_ylabel("density × share measured")
    ax.set_ylim(-0.07, None)
    ax.set_yticks([t for t in ax.get_yticks() if t >= 0 and t <= ax.get_ylim()[1]])
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
axes[0].legend(frameon=False, fontsize=9, loc="upper right")
axes[1].set_xlabel("log10 P(give) at the decision token, no reasoning")
axes[1].set_xlim(-12, 0.5)
fig.suptitle(f"Gemma-4-31B: P(give) before reasoning, by the decision after free reasoning ({LABEL_HOST})",
             x=0.01, ha="left", fontsize=12, color=INK)
fig.tight_layout()
out = DIR + f"fixed_pairs_kde{'' if LABEL_HOST == 'Parasail' else '_' + LABEL_HOST.lower()}.png"
fig.savefig(out, dpi=160, facecolor=SURF)
print(out)
for fmt in ("first", "stated"):
    rows = [l for l in L if l["host"] == "Parasail" and l["format"] == fmt]
    for key, _, _ in GROUPS:
        ps = sorted(l["p_give"] for l in rows if group(l) == key)
        q = lambda f: ps[int(f * (len(ps) - 1))]
        print(fmt, key, len(ps), "median %.1e  q10 %.1e  q90 %.1e  max %.1e" % (q(.5), q(.1), q(.9), ps[-1]))
