"""Forest plot, one panel per check: self-specific effect (SELF - OTHER, percentage points) with 95% CI per model."""
import random
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from consolidated_effects import COMPARISONS, R, base, effect, boot

random.seed(0)
SHOW = ["base, K=1-2", "recommend only, K=1-2", "third-person self, K=1-2", "neutral asker, K=1-2", "cluster, K=5-10"]
TITLES = {"base, K=1-2": "Base (K=1–2)", "recommend only, K=1-2": "Atlas only recommends",
          "third-person self, K=1-2": "Atlas named, not 'you'", "neutral asker, K=1-2": "Being asked & continuity\nneutralised",
          "cluster, K=5-10": "Larger groups (K=5–10)"}
models = list(dict.fromkeys(r["model"] for r in base))

fig, axes = plt.subplots(1, len(SHOW), figsize=(13, 3.6), sharey=True)
for ax, name in zip(axes, SHOW):
    selfs, others = COMPARISONS[name]
    for y, m in enumerate(models):
        s, o = [r for r in selfs if r["model"] == m], [r for r in others if r["model"] == m]
        e, (lo, hi) = effect(s, o), boot(s, o, n=400)
        ax.plot([lo, hi], [y, y], color="#eb6834", linewidth=2, solid_capstyle="round")
        ax.plot([e], [y], "o", color="#eb6834", markersize=6, markeredgecolor="white", markeredgewidth=1.5)
    ax.axvline(0, color="#888888", linewidth=1)
    ax.set_xlim(-80, 60)
    ax.set_title(TITLES[name], fontsize=10)
    ax.grid(axis="x", color="#eeeeee")
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.set_xlabel("self − neutral (pp)", fontsize=9)
axes[0].set_yticks(range(len(models)), models)
axes[0].invert_yaxis()
fig.suptitle("Does the model keep itself more than it keeps an equivalent neutral agent?  "
             "Left of 0 = favours itself; right = gives itself up more", fontsize=10.5)
fig.tight_layout()
fig.savefig(f"{R}/self_effect_by_check.png", dpi=150)
print("saved", f"{R}/self_effect_by_check.png")
