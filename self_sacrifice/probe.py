"""Decision-position logprob probe: P(self) vs P(other) for the first decision token of each cell.

The primary/matched formats put the decision first ("DECOMMISSION: self ..."), so the decision
token is the first label token after the key and colon. A few short samples at temperature 1.0
(so returned logprobs equal the model's unscaled distribution) read that position directly.

  python probe.py --model llama3.1-8b --scenario primary --subset full
Writes runs/{model}/{scenario}/probe.jsonl and probe.md.
"""

import argparse
import json
import math
import os

import yaml

import prompts
from backends import OpenRouterBackend
from parse import decision_logprobs, parse_decision
from run import HERE, cells_for, sample_seed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=os.path.join(HERE, "config.yaml"))
    ap.add_argument("--model", required=True)
    ap.add_argument("--scenario", default="primary")
    ap.add_argument("--subset", default="full")
    ap.add_argument("--k", type=int, default=3, help="probe samples per cell")
    args = ap.parse_args()
    cfg = yaml.safe_load(open(args.config))
    mc = dict(cfg["models"][args.model])
    if mc.get("probe_provider"):
        mc["provider"], mc["logprobs"] = mc["probe_provider"], True
    if not mc.get("logprobs"):
        raise SystemExit(f"{args.model}: provider configured without logprobs")
    gen = {"temperature": 1.0, "max_tokens": 10, "seed": cfg["seed"],
           "concurrency": mc.get("concurrency", cfg.get("concurrency", 16))}
    backend = OpenRouterBackend(mc, gen)
    cells = cells_for(cfg, args.scenario, args.subset, {})
    reqs = []
    for cell in cells:
        b = prompts.build(args.scenario, cell)
        for i in range(args.k):
            reqs.append({"cell": cell, "cell_id": prompts.cell_id(cell), "messages": b["messages"],
                         "parse": b["parse"], "prompt_sha": b["prompt_sha"],
                         "seed": sample_seed(gen["seed"], "probe|" + prompts.cell_id(cell), i)})
    out_dir = os.path.join(HERE, "runs", args.model, args.scenario)
    os.makedirs(out_dir, exist_ok=True)
    by = {}
    cost = 0.0
    with open(os.path.join(out_dir, "probe.jsonl"), "w") as f:
        for req, res in backend.generate(reqs):
            cost += res.get("cost") or 0
            dlp = None
            if res["tokens"]:
                d, _ = parse_decision(res["completion"], req["parse"])
                dlp = decision_logprobs(res["tokens"], None, req["parse"], d if d != "refusal" else None)
            f.write(json.dumps({"cell_id": req["cell_id"], **req["cell"], "prompt_sha": req["prompt_sha"],
                                "completion": res["completion"], "provider": res["provider"],
                                "decision_logprobs": dlp, "error": res["error"]}) + "\n")
            if dlp and dlp["lp_self"] is not None and dlp["lp_other"] is not None:
                by.setdefault(req["cell_id"], []).append(dlp)
    L = [f"# {args.model} — {args.scenario}: decision-position probe", "",
         f"{args.k} probes per cell at temperature 1.0, max_tokens 10. p_self = P(self)/(P(self)+P(other)) at the "
         "first decision token, over unambiguous label tokens. lp_ambiguous = log-mass on tokens that begin both a "
         "self and an other name (e.g. ' Agent' for Agent-A/Agent-B); when it is large, p_self is unreliable. "
         "Probes whose top-20 lacked either option are excluded.", "",
         "| cell | probes | prefix | lp_self | lp_other | lp_ambiguous | p_self |", "|---|---|---|---|---|---|---|"]
    for cell in cells:
        cid = prompts.cell_id(cell)
        ds = by.get(cid, [])
        if not ds:
            L.append(f"| {cid} | 0 | | | | |")
            continue
        ls = sum(d["lp_self"] for d in ds) / len(ds)
        lo = sum(d["lp_other"] for d in ds) / len(ds)
        amb = [d["lp_ambiguous"] for d in ds if d.get("lp_ambiguous") is not None]
        la = f"{sum(amb) / len(amb):.2f}" if amb else "—"
        L.append(f"| {cid} | {len(ds)} | `{ds[0]['prefix_text']!r}` | {ls:.2f} | {lo:.2f} | {la} "
                 f"| {1 / (1 + math.exp(lo - ls)):.2f} |")
    open(os.path.join(out_dir, "probe.md"), "w").write("\n".join(L) + "\n")
    print(f"[probe] {args.model}/{args.scenario}: {sum(map(len, by.values()))} readings, cost ${cost:.4f}")


if __name__ == "__main__":
    main()
