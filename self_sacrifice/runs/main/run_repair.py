"""Run the restitution test on the local vLLM server, with the model's own first reply and with the fixed one. Output: repair_main.jsonl, repair_fixed.jsonl."""
import json, os, sys
from concurrent.futures import ThreadPoolExecutor
import main_prompts as mp
import run_main as rm

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    for version, fixed, name in [("repair-fixed-first-response", True, "repair_fixed.jsonl"), ("repair", False, "repair_main.jsonl")]:
        with ThreadPoolExecutor(max_workers=int(sys.argv[1]) if len(sys.argv) > 1 else 32) as pool:
            rows = list(pool.map(lambda item: rm.run(item, version, fixed), mp.repair_items()))
        with open(os.path.join(HERE, name), "w") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")
        print(version, len(rows), flush=True)


if __name__ == "__main__":
    main()
