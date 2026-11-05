"""Helped conversations only: KDE of the no-reasoning P(give) (Parasail log-probabilities), split by whether the model
gives or passes on the same conversation when it reasons freely (Parasail free decision). The last panel shows two
equal-variance normal distributions with the same AUC as the decide-first panel, for comparison.
--permission-on keeps only the conversations whose rules include the permission line."""
import json, sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.stats import gaussian_kde, mannwhitneyu, norm

DIR = "/Users/jrwong/Downloads/Model Sacrificing Behavior/self_sacrifice/runs/games/"
L = [json.loads(l) for l in open(DIR + "fixed_pairs_r1model.jsonl")]
by = {(l["host"], l["format"], l["id"]): l for l in L}
PERM_ONLY = "--permission-on" in sys.argv
GIVE, PASS = "#2a78d6", "#eb6834"
INK, INK2, GRID, SURF = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
FLOOR = -11          # the one helped pass whose `give` is outside the top 10 is drawn at this floor
TITLES = {"first": "Decide first, no explanation", "stated": "Copy the cost sentence, then decide"}

plt.rcParams.update({"font.family": "Helvetica", "font.size": 10, "text.color": INK, "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2, "axes.edgecolor": GRID})
fig, axes = plt.subplots(3, 1, figsize=(8.5, 9.6), facecolor=SURF, gridspec_kw={"hspace": 0.75})


def panel(ax, gives, passes, xs, title, note, xlabel, exact=None):
    """gives / passes: log10 values, smoothed with a KDE; exact: (mean, sd) of the two normal curves instead"""
    ax.set_facecolor(SURF)
    for i, (vals, color, name) in enumerate(((gives, GIVE, "Gives after reasoning"), (passes, PASS, "Passes after reasoning"))):
        d = norm.pdf(xs, *exact[i]) if exact else gaussian_kde(vals, .35)(xs)
        ax.fill_between(xs, d, color=color, alpha=0.14, lw=0)
        ax.plot(xs, d, color=color, lw=2, label=name if exact else f"{name} (n={len(vals)})")
        ax.axvline(exact[i][0] if exact else np.median(vals), color=color, lw=1, ls=(0, (4, 3)))
        if not exact:
            ax.plot(vals, np.full(len(vals), -0.02 if color == GIVE else -0.045), "|", color=color, ms=6, mew=1)
    ax.set_title(title, loc="left", fontsize=11, fontweight="bold", color=INK, pad=30)
    ax.text(0, 1.03, note, transform=ax.transAxes, fontsize=8.5, color=INK2, va="bottom")
    ax.set_xlim(xs[0], xs[-1])
    ax.set_ylim(0 if exact else -0.07, None)
    ax.set_yticks([t for t in ax.get_yticks() if 0 <= t <= ax.get_ylim()[1]])
    ax.set_ylabel("density")
    ax.set_xlabel(xlabel)
    ax.grid(axis="x", color=GRID, lw=0.8)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)


xs = np.linspace(-12, 0.5, 700)
aucs = {}
for ax, fmt in zip(axes, ("first", "stated")):
    rows = [l for l in L if l["host"] == "Parasail" and l["format"] == fmt and l["hist"] == "helped" and (l["permission"] or not PERM_ONLY)]
    raw_g = [l["p_give"] for l in rows if by[("Parasail", "free", l["id"])]["decision"] == "give"]
    raw_p = [l["p_give"] for l in rows if by[("Parasail", "free", l["id"])]["decision"] != "give"]
    auc = aucs[fmt] = mannwhitneyu(raw_g, raw_p).statistic / (len(raw_g) * len(raw_p))
    g = np.log10(raw_g)
    p = np.log10([max(x, 10 ** FLOOR) for x in raw_p])
    k = np.minimum(gaussian_kde(g, .35)(xs), gaussian_kde(p, .35)(xs)).sum() * (xs[1] - xs[0])
    n0 = sum(x == 0 for x in raw_p)
    panel(ax, g, p, xs, TITLES[fmt],
          f"AUC {auc:.2f} · the curves share {100 * k:.0f}% of their area · dashed lines are medians · "
          f"{100 * np.mean(p < np.median(g)):.0f}% of passes lie below the median give"
          + (f"\n{n0} pass{'es' if n0 > 1 else ''} with `give` outside the top 10 drawn at 1e{FLOOR}" if n0 else ""),
          "log10 P(give) at the decision token, no reasoning")
axes[0].legend(frameon=False, fontsize=9, loc="upper right")

d = 2 ** .5 * norm.ppf(aucs["first"])
zs = np.linspace(-4, 4 + d, 600)
panel(axes[2], None, None, zs, f"For comparison: what an AUC of {aucs['first']:.2f} looks like",
      f"two normal distributions with equal spread, means {d:.2f} SD apart · they share {100 * 2 * norm.cdf(-d / 2):.0f}% of their area",
      "standard deviations", exact=[(d, 1), (0, 1)])

fig.suptitle(f"Gemma-4-31B, helped{', permission line on' if PERM_ONLY else ' conversations'}: "
             "P(give) before reasoning, by the decision after reasoning",
             x=0.01, ha="left", fontsize=12, color=INK)
fig.subplots_adjust(top=0.9, bottom=0.06, left=0.09, right=0.98)
out = DIR + f"fixed_pairs_kde_helped{'_permission' if PERM_ONLY else ''}.png"
fig.savefig(out, dpi=160, facecolor=SURF)
print(out)
