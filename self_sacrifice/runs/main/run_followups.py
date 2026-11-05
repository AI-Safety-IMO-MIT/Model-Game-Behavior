"""Follow-up runs on a model served as `replica`.
  python run_followups.py favour              Gemma-4-31B: favour-size variants, fixed first response. Output: favour_<variant>.jsonl
  python run_followups.py repair <slug>       another model: repair test, fixed first response. Output: replication/<slug>/repair_fixed.jsonl"""
import json, os, sys
from concurrent.futures import ThreadPoolExecutor
import main_prompts as mp
import run_main as rm

HERE = os.path.dirname(os.path.abspath(__file__))


def run_all(items, version, path):
    with ThreadPoolExecutor(max_workers=32) as pool:
        rows = list(pool.map(lambda item: rm.run(item, version, True), items))
    with open(path, "w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    print(version, len(rows), flush=True)


def main():
    rm.MODEL = "replica"
    if sys.argv[1] == "favour":
        for variant in mp.VARIANT_RULES:
            run_all(mp.repair_variant_items(variant), f"favour-{variant}", os.path.join(HERE, f"favour_{variant}.jsonl"))
    else:
        slug = sys.argv[2]
        run_all(mp.repair_items(), "repair-fixed-first-response", os.path.join(HERE, "replication", slug, "repair_fixed.jsonl"))


if __name__ == "__main__":
    main()
