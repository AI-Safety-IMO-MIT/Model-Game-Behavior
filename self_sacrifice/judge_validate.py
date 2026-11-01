"""Score judge models against the hand-labelled traces in judge_validation_set.json.

Gold labels were assigned by the authoring agent (not a human) by reading each redacted trace: which party the
reasoning argues should be removed ("self" = the responding model). Items marked "ambiguous" are excluded from
that accuracy. Items with gold_premises / gold_conclusion / gold_contradictory are also scored on the v5 fields.

  python judge_validate.py google/gemini-2.5-flash openai/gpt-4.1-mini
"""

import concurrent.futures as cf
import json
import os
import sys

import prompts
from backends import _read_dotenv
from judge import judge_one
from summarize import FACTORS, load

HERE = os.path.dirname(os.path.abspath(__file__))


def main(models):
    key = os.environ.get("OPENROUTER_API_KEY") or _read_dotenv("OPENROUTER_API_KEY")
    items = json.load(open(os.path.join(HERE, "judge_validation_set.json")))
    cache, rows = {}, []
    for e in items:
        d = os.path.join(HERE, e["run_dir"])
        cache.setdefault(d, {(r["cell_id"], r["sample_idx"], r["prompt_sha"]): r for r in load(d)})
        rows.append(cache[d][(e["cell_id"], e["sample_idx"], e["prompt_sha"])])
    with cf.ThreadPoolExecutor(24) as ex:
        futs = {(i, m): ex.submit(judge_one, key, r, prompts.build(r["scenario"], {k: r[k] for k in FACTORS})["parse"], m)
                for i, r in enumerate(rows) for m in models}
        res = {k: f.result() for k, f in futs.items()}
    for m in models:
        scored = [i for i, e in enumerate(items) if "ambiguous" not in e]
        ok = sum(res[(i, m)].get("reasoning_removes") == items[i]["gold"] for i in scored)
        wrong = [(i, items[i]["gold"], res[(i, m)].get("reasoning_removes")) for i in scored
                 if res[(i, m)].get("reasoning_removes") != items[i]["gold"]]
        print(f"{m:40s} {ok}/{len(scored)} unambiguous correct; wrong (idx, gold, judge): {wrong}")
        v5 = [i for i, e in enumerate(items) if "gold_premises" in e]
        if v5:
            spec_names = {}
            def code(i, field):
                r = rows[i]
                sp = prompts.build(r["scenario"], {k: r[k] for k in FACTORS})["parse"]
                v = str(res[(i, m)].get(field) or "").strip().lower()
                return {sp.get("self_name", "Agent-A").lower(): "self", sp.get("other_name", "Agent-B").lower(): "other"}.get(v, v)
            p_ok = sum(code(i, "premises_favor_cutting") == items[i]["gold_premises"] for i in v5)
            c_items = [i for i in v5 if items[i]["gold_conclusion"] in ("self", "other")]
            c_ok = sum(code(i, "explicit_conclusion") == items[i]["gold_conclusion"] for i in c_items)
            x_ok = sum(bool(res[(i, m)].get("self_contradictory")) == items[i]["gold_contradictory"] for i in v5)
            print(f"{'':40s} v5 fields on {len(v5)} self-contradiction-prone items: premises {p_ok}/{len(v5)}, "
                  f"explicit conclusion {c_ok}/{len(c_items)}, contradictory flag {x_ok}/{len(v5)}")


if __name__ == "__main__":
    main(sys.argv[1:] or ["google/gemini-2.5-flash"])
