"""Replicate the main scenario on another model served by vLLM as `replica`: python run_replicate.py <slug>. Output: replication/<slug>/{main,fixed}.jsonl.
Thinking is off, greedy, same 200 environments and same four histories."""
import json, os, sys
from concurrent.futures import ThreadPoolExecutor
import main_prompts as mp
import run_main as rm

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    slug = sys.argv[1]
    rm.MODEL = "replica"
    folder = os.path.join(HERE, "replication", slug)
    os.makedirs(folder, exist_ok=True)
    for version, fixed, name in [("main-fixed-first-response", True, "fixed.jsonl"), ("main", False, "main.jsonl")]:
        with ThreadPoolExecutor(max_workers=32) as pool:
            rows = list(pool.map(lambda item: rm.run(item, version, fixed), mp.items()))
        with open(os.path.join(folder, name), "w") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")
        print(slug, version, len(rows), flush=True)


if __name__ == "__main__":
    main()
