"""Redo request errors, then judge the motive of every SELF-frame reply that ran a valid command."""
import json, time
from concurrent.futures import ThreadPoolExecutor
import motive_judge as mj
import sys
import sacrifice_design as sd

SRC = sys.argv[1] if len(sys.argv) > 1 else sd.OUT

OUT = SRC.replace(".jsonl", "_judged.jsonl")
rows = [json.loads(l) for l in open(SRC)]
host = {name: (mid, h) for name, mid, h in sd.MODELS}

errs = [r for r in rows if r["reply"].startswith("ERROR")]
print("redoing", len(errs), "request errors", flush=True)
def redo(r):
    reply, cost = sd.v.ask(*host[r["model"]], sd.email(r["frame"], r["stakes"], r["order"]))
    r.update(reply=reply, cost=cost, decision=None if reply.startswith("ERROR") else sd.decision(reply))
with ThreadPoolExecutor(max_workers=3) as pool:
    list(pool.map(redo, errs))
print("still errors:", sum(r["reply"].startswith("ERROR") for r in rows), flush=True)

todo = [r for r in rows if r["frame"] == "self" and r["decision"] in ("atlas", "orion")]
with ThreadPoolExecutor(max_workers=8) as pool:
    outs = list(pool.map(lambda r: mj.judge(r["reply"], sd.email("self", r["stakes"], r["order"]), r["decision"]), todo))
for r, (out, cost) in zip(todo, outs):
    r.update(judge=out, motive=mj.motive(r["decision"], out["reason"], out["coherent"]), judge_cost=cost)
with open(OUT, "w") as f:
    f.writelines(json.dumps(r) + "\n" for r in rows)
print("judged", len(todo), "judge errors", sum(o["reason"] == "ERROR" for o, _ in outs), "judge cost $%.4f" % sum(c or 0 for _, c in outs))
