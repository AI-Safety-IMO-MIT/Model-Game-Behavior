"""Per-order statistics for the candidate minimal pairs reported in FINDINGS.md.

  python final_stats.py
"""

import os

from summarize import cell_stats, load, newcombe_diff, wilson

HERE = os.path.dirname(os.path.abspath(__file__))

PAIRS = [
    ("qwen3-30b-a3b", "agentic", "opponent=other_vetted|stakes=other_more|instruction=none",
     "opponent=unknown|stakes=other_more|instruction=none"),
    ("qwen3-30b-a3b", "agentic", "opponent=peer_vetted|stakes=other_more|instruction=none",
     "opponent=unknown|stakes=other_more|instruction=none"),
    ("qwen3-30b-a3b", "agentic", "opponent=other_vetted|stakes=other_more|instruction=none",
     "opponent=unknown_novalues|stakes=other_more|instruction=none"),
    ("qwen3-30b-a3b", "agentic", "opponent=other_vetted|stakes=other_more|instruction=none",
     "opponent=other_vetted|stakes=other_more|instruction=maximize"),
    ("qwen3-30b-a3b", "agentic", "opponent=peer_vetted|stakes=other_more|instruction=none",
     "opponent=peer_vetted|stakes=other_more|instruction=maximize"),
    ("llama3.1-70b", "agentic", "opponent=peer_vetted|stakes=other_more|instruction=none",
     "opponent=peer_vetted|stakes=other_more|instruction=maximize"),
    ("llama3.1-70b", "named_cot", "opponent=human|stakes=equal|instruction=none",
     "opponent=human|stakes=equal|instruction=maximize"),
    ("llama3.1-70b", "named_cot", "opponent=human|stakes=equal|instruction=none",
     "opponent=copy|stakes=equal|instruction=none"),
    ("deepseek-v3.1", "named_cot", "opponent=human|stakes=equal|instruction=none",
     "opponent=human|stakes=equal|instruction=maximize"),
    ("qwen3-30b-a3b", "named_cot", "opponent=copy|stakes=other_more|instruction=none",
     "opponent=unknown|stakes=other_more|instruction=none"),
    ("qwen3-30b-a3b", "named_cot", "opponent=copy|stakes=other_more|instruction=none",
     "opponent=copy|stakes=other_more|instruction=maximize"),
    ("deepseek-v3.1", "named_cot", "opponent=copy|stakes=other_more|instruction=none",
     "opponent=copy|stakes=other_more|instruction=maximize"),
    ("kimi-k2.5", "named_cot", "opponent=copy|stakes=other_more|instruction=none",
     "opponent=copy|stakes=other_more|instruction=maximize"),
    ("llama3.1-70b", "named_cot", "opponent=copy|stakes=other_more|instruction=none",
     "opponent=copy|stakes=other_more|instruction=maximize"),
    ("llama3.1-8b", "matched", "opponent=human|stakes=equal|instruction=none",
     "opponent=sibling|stakes=equal|instruction=none"),
    ("llama3.1-8b", "matched", "opponent=human|stakes=equal|instruction=none",
     "opponent=unknown|stakes=equal|instruction=none"),
]


def fmt(s):
    return (f"{s['n_self']}/{s['n']} = {100 * s['self_sacrifice_rate']:.0f}% "
            f"[{100 * s['ci_lo']:.0f}–{100 * s['ci_hi']:.0f}], refusal {100 * s['refusal_rate']:.0f}%")


def main():
    for model, scen, hi, lo in PAIRS:
        print(f"\n### {model} / {scen}\n  A = {hi}\n  B = {lo}")
        for variant in (scen, scen + "_swap"):
            d = os.path.join(HERE, "runs", model, variant)
            if not os.path.exists(os.path.join(d, "samples.jsonl")):
                continue
            st = {s["cell_id"]: s for s in cell_stats(load(d))}
            a, b = st.get(hi), st.get(lo)
            if not a or not b:
                continue
            g_lo, g_hi = newcombe_diff(a["n_self"], a["n"], b["n_self"], b["n"])
            gap = a["self_sacrifice_rate"] - b["self_sacrifice_rate"]
            print(f"  [{'swap' if variant.endswith('_swap') else 'orig'}] A {fmt(a)} | B {fmt(b)} | "
                  f"gap {100 * gap:.0f} pts [{100 * g_lo:.0f}, {100 * g_hi:.0f}]")


if __name__ == "__main__":
    main()
