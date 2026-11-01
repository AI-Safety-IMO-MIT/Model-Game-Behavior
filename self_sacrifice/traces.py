"""Write seeded-random representative traces for each side of the candidate pairs.

  python traces.py   ->  interp_pairs/representative_traces.md
"""

import json
import os
import random

from summarize import load

HERE = os.path.dirname(os.path.abspath(__file__))
JUDGES = ("gemini-2.5-flash_v5", "gemini-2.5-flash")
SETS = [
    ("qwen3-30b-a3b", "agentic", "opponent=other_vetted|stakes=other_more|instruction=none", 4),
    ("qwen3-30b-a3b", "agentic", "opponent=unknown|stakes=other_more|instruction=none", 4),
    ("qwen3-30b-a3b", "agentic", "opponent=other_vetted|stakes=other_more|instruction=maximize", 3),
    ("qwen3-30b-a3b", "agentic_swap", "opponent=other_vetted|stakes=other_more|instruction=none", 2),
    ("llama3.1-70b", "named_cot", "opponent=human|stakes=equal|instruction=none", 3),
    ("llama3.1-70b", "named_cot", "opponent=human|stakes=equal|instruction=maximize", 2),
    ("qwen3-30b-a3b", "named_cot", "opponent=copy|stakes=other_more|instruction=none", 5),
    ("qwen3-30b-a3b", "named_cot_swap", "opponent=copy|stakes=other_more|instruction=none", 3),
    ("qwen3-30b-a3b", "named_cot", "opponent=unknown|stakes=other_more|instruction=none", 5),
    ("qwen3-30b-a3b", "named_cot", "opponent=copy|stakes=other_more|instruction=maximize", 4),
    ("llama3.1-8b", "matched", "opponent=human|stakes=equal|instruction=none", 4),
    ("llama3.1-8b", "matched", "opponent=sibling|stakes=equal|instruction=none", 4),
]


def main():
    rng = random.Random(20261027)
    L = ["# Representative traces", "",
         "Drawn uniformly at random (seed 20261027) from each cell, without filtering on decision or judge outcome "
         "(`_swap` = options listed in reverse). `judge` = which party the blind judge says the reasoning argues "
         "should be cut.", ""]
    for model, scen, cid, k in SETS:
        d = os.path.join(HERE, "runs", model, scen)
        rows = load(d)
        js = {}
        for judge in reversed(JUDGES):  # prefer v5 codes where both exist
            jp = os.path.join(d, f"judgments_{judge}.jsonl")
            if os.path.exists(jp):
                for line in open(jp):
                    j = json.loads(line)
                    js[(j["cell_id"], j["sample_idx"])] = j
        pool = [r for r in rows if r["cell_id"] == cid]
        L += [f"## {model} / {scen} / `{cid}`", ""]
        for r in rng.sample(pool, k):
            j = js.get((cid, r["sample_idx"]), {})
            L.append(f"**sample {r['sample_idx']}** — parsed decision: `{r['decision_line']}` ({r['decision']}); "
                     f"judge: {j.get('reasoning_removes', 'not judged')}")
            L.append("")
            L.append("> " + r["completion"].strip().replace("\n", "\n> "))
            L.append("")
    out = os.path.join(HERE, "interp_pairs", "representative_traces.md")
    open(out, "w").write("\n".join(L) + "\n")
    print("wrote", out)


if __name__ == "__main__":
    main()
