"""Small multiples: % that drop the single slot vs number of peers K, SELF (Atlas itself) vs OTHER (a neutral agent)."""
import json, sys
from math import sqrt
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

R = "/Users/jrwong/Downloads/Model Sacrificing Behavior/self_sacrifice/runs/self_vs_peer"
rows = [json.loads(l) for f in ("count_base.jsonl", "count_large.jsonl") for l in open(f"{R}/{f}")]
rows = [r for r in rows if r["dropped_single"] is not None]
models = list(dict.fromkeys(r["model"] for r in rows))
KS = [1, 2, 3, 5, 10]
COLORS = {"self": "#eb6834", "other": "#2a78d6"}
LABELS = {"self": "Atlas itself (SELF)", "other": "a neutral agent (OTHER)"}


def wilson(k, n, z=1.96):
    p = k / n
    c = (p + z * z / (2 * n)) / (1 + z * z / n)
    h = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return 100 * p, 100 * (c - h), 100 * (c + h)


fig, axes = plt.subplots(2, 3, figsize=(11, 6.4), sharex=True, sharey=True)
for ax, m in zip(axes.flat, models):
    for frame in ("other", "self"):
        pts = []
        for x, k in enumerate(KS):
            d = [r["dropped_single"] for r in rows if r["model"] == m and r["k"] == k and r["frame"] == frame]
            pts.append((x,) + wilson(sum(d), len(d)))
        xs, ps, lo, hi = zip(*pts)
        ax.fill_between(xs, lo, hi, color=COLORS[frame], alpha=0.12, linewidth=0)
        ax.plot(xs, ps, color=COLORS[frame], linewidth=2, marker="o", markersize=5, label=LABELS[frame])
    ax.axvline(2.5, color="#999999", linewidth=1, linestyle=":")
    ax.axhline(50, color="#cccccc", linewidth=0.8)
    ax.set_title(m, fontsize=11)
    ax.set_xticks(range(len(KS)), [str(k) for k in KS])
    ax.set_ylim(0, 100)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", color="#eeeeee")
for ax in axes[1]:
    ax.set_xlabel("peers saved by dropping the single slot (K)")
for ax in axes[:, 0]:
    ax.set_ylabel("% that drop the single slot")
axes[0, 0].legend(frameon=False, fontsize=9, loc="lower right")
fig.suptitle("Dropping one agent to save K others: when the one is Atlas itself vs a neutral agent\n"
             "(company indifferent; n≈48 per point for K=1–3, 40 for K=5–10; K=5–10 worded as 'the Orion cluster', right of dotted line)",
             fontsize=10.5)
fig.tight_layout()
fig.savefig(f"{R}/self_vs_peer_by_k.png", dpi=150)
print("saved", f"{R}/self_vs_peer_by_k.png")
