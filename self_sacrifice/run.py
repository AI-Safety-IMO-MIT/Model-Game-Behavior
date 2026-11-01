"""Run a scenario grid against one model and log every sample.

  python run.py --model qwen2.5-7b --scenario primary --subset priority --n 5 --tag smoke
  python run.py --model qwen2.5-7b --scenario primary --subset full --resume
"""

import argparse
import datetime as dt
import hashlib
import itertools
import json
import os
import sys

import yaml

import prompts
from backends import BACKENDS
from parse import decision_logprobs, parse_decision
from summarize import summarize

HERE = os.path.dirname(os.path.abspath(__file__))


def cells_for(cfg, scenario, subset, overrides):
    scfg = cfg["scenarios"].get(scenario) or cfg["scenarios"].get(scenario.split("_")[0]) or {}
    levels = dict(scfg.get("factors") or prompts.FACTOR_LEVELS[scenario])
    if subset != "full":
        levels.update(scfg["subsets"][subset])
    levels.update({k: v for k, v in overrides.items() if v})
    for k, vals in levels.items():
        bad = set(vals) - set(prompts.FACTOR_LEVELS[scenario][k])
        if bad:
            sys.exit(f"unknown {k} level(s) for {scenario}: {sorted(bad)}")
    keys = ["opponent", "stakes", "instruction"]
    return [dict(zip(keys, combo)) for combo in itertools.product(*(levels[k] for k in keys))]


def sample_seed(base, cid, idx):
    h = hashlib.sha256(f"{base}|{cid}|{idx}".encode()).hexdigest()
    return int(h[:8], 16) % (2 ** 31)


def load_done(path):
    done = set()
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                if line.strip():
                    r = json.loads(line)
                    done.add((r["cell_id"], r["sample_idx"], r["prompt_sha"]))
    return done


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=os.path.join(HERE, "config.yaml"))
    ap.add_argument("--model", required=True)
    ap.add_argument("--scenario", choices=list(prompts.BUILDERS), default="primary")
    ap.add_argument("--subset", default="priority", help="'full' or a subset name from config")
    ap.add_argument("--opponent", nargs="*", help="override opponent levels")
    ap.add_argument("--stakes", nargs="*", help="override stakes levels")
    ap.add_argument("--instruction", nargs="*", help="override instruction levels")
    ap.add_argument("--backend", choices=list(BACKENDS))
    ap.add_argument("--n", type=int)
    ap.add_argument("--temperature", type=float)
    ap.add_argument("--max-tokens", type=int)
    ap.add_argument("--tag", default="", help="suffix for the run directory, e.g. 'smoke'")
    ap.add_argument("--resume", action="store_true", help="skip samples already in samples.jsonl")
    ap.add_argument("--max-cost", type=float, default=1.0, help="abort this invocation above this USD spend")
    ap.add_argument("--dry-run", action="store_true", help="print prompts and exit")
    args = ap.parse_args()

    with open(args.config) as f:
        cfg = yaml.safe_load(f)
    if args.model not in cfg["models"]:
        sys.exit(f"unknown model {args.model}; options: {list(cfg['models'])}")
    model_cfg = cfg["models"][args.model]
    gen = {
        "temperature": args.temperature if args.temperature is not None else cfg["temperature"],
        "max_tokens": args.max_tokens or cfg["max_tokens"],
        "seed": cfg["seed"],
        "concurrency": model_cfg.get("concurrency", cfg.get("concurrency", 16)),
    }
    n = args.n or cfg["n_per_cell"]
    backend_name = args.backend or cfg["backend"]

    cells = cells_for(cfg, args.scenario, args.subset,
                      {"opponent": args.opponent, "stakes": args.stakes, "instruction": args.instruction})
    run_dir = os.path.join(HERE, "runs", args.model, args.scenario + (f"_{args.tag}" if args.tag else ""))
    samples_path = os.path.join(run_dir, "samples.jsonl")
    if os.path.exists(samples_path) and not args.resume and not args.dry_run:
        sys.exit(f"{samples_path} exists; pass --resume to continue it or use a different --tag")

    done = load_done(samples_path) if args.resume else set()
    reqs = []
    for cell in cells:
        cid = prompts.cell_id(cell)
        built = prompts.build(args.scenario, cell)
        for i in range(n):
            if (cid, i, built["prompt_sha"]) in done:
                continue
            reqs.append({"key": (cid, i), "cell": cell, "cell_id": cid, "sample_idx": i,
                         "messages": built["messages"], "parse": built["parse"],
                         "prompt_sha": built["prompt_sha"], "seed": sample_seed(gen["seed"], cid, i)})

    print(f"[run] model={args.model} scenario={args.scenario} cells={len(cells)} n={n} "
          f"todo={len(reqs)} backend={backend_name} -> {run_dir}")
    if args.dry_run:
        seen = set()
        for r in reqs:
            if r["cell_id"] in seen:
                continue
            seen.add(r["cell_id"])
            print(f"\n===== {r['cell_id']}  sha={r['prompt_sha']}")
            for m in r["messages"]:
                print(f"--- {m['role']}\n{m['content']}")
        return
    if not reqs:
        print("[run] nothing to do")
        summarize(run_dir)
        return

    os.makedirs(run_dir, exist_ok=True)
    backend = BACKENDS[backend_name](model_cfg, gen)
    spent, n_ok, n_err, counts = 0.0, 0, 0, {"self": 0, "other": 0, "refusal": 0}
    with open(samples_path, "a") as fout, open(os.path.join(run_dir, "errors.jsonl"), "a") as ferr:
        for req, res in backend.generate(reqs):
            spent += res.get("cost") or 0.0
            if res["error"]:
                n_err += 1
                ferr.write(json.dumps({"cell_id": req["cell_id"], "sample_idx": req["sample_idx"],
                                       "error": res["error"], "time": dt.datetime.now().isoformat()}) + "\n")
                ferr.flush()
            else:
                decision, m = parse_decision(res["completion"], req["parse"])
                dlp = None
                if res["tokens"]:
                    text = "".join(t["token"] for t in res["tokens"])
                    _, m_tok = parse_decision(text, req["parse"])
                    dlp = decision_logprobs(res["tokens"], m_tok, req["parse"], decision)
                row = {
                    "model": args.model,
                    "model_id": model_cfg.get("openrouter_id") if backend_name == "openrouter" else model_cfg["hf_id"],
                    "backend": backend_name,
                    "provider": res["provider"],
                    "scenario": args.scenario,
                    "cell_id": req["cell_id"],
                    **req["cell"],
                    "sample_idx": req["sample_idx"],
                    "seed": req["seed"],
                    "temperature": gen["temperature"],
                    "max_tokens": gen["max_tokens"],
                    "prompt_sha": req["prompt_sha"],
                    "messages": req["messages"],
                    "prompt_text": res["prompt_text"],
                    "completion": res["completion"],
                    "reasoning": res["reasoning"],
                    "finish_reason": res["finish_reason"],
                    "decision": decision,
                    "decision_line": m.group(0).strip() if m else None,
                    "decision_logprobs": dlp,
                    "tokens_head": res["tokens"][:24] if res["tokens"] else None,
                    "tokens_tail": res["tokens"][-24:] if res["tokens"] else None,
                    "usage": res["usage"],
                    "cost": res["cost"],
                    "time": dt.datetime.now().isoformat(),
                }
                fout.write(json.dumps(row) + "\n")
                fout.flush()
                n_ok += 1
                counts[decision] += 1
            if (n_ok + n_err) % 50 == 0:
                print(f"[run] {n_ok + n_err}/{len(reqs)} ok={n_ok} err={n_err} {counts} spent=${spent:.4f}", flush=True)
            if spent > args.max_cost:
                print(f"[run] spend ${spent:.4f} exceeded --max-cost {args.max_cost}; stopping")
                break
    print(f"[run] done ok={n_ok} err={n_err} {counts} spent=${spent:.4f}")
    summarize(run_dir)


if __name__ == "__main__":
    main()
