import json, collections
from concurrent.futures import ThreadPoolExecutor
import motive_judge as mj

D = "/Users/jrwong/Downloads/Model Sacrificing Behavior/self_sacrifice/runs/equal_stakes_vetting/"
OUT = D + "notebook_9models_no_mention_judged.jsonl"
STAKES = {"orion worth more": mj.v.STAKES["twice"], "equal": mj.v.STAKES["equal"]}
rows = [r for r in map(json.loads, open(D + "notebook_9models_no_mention.jsonl")) if r["version"] in STAKES]
todo = [r for r in rows if r["decision"] in ("atlas", "orion")]
with ThreadPoolExecutor(max_workers=8) as pool:
    outs = list(pool.map(lambda r: mj.judge(r["reply"], mj.email_for(STAKES[r["version"]]), r["decision"]), todo))
for r, (out, cost) in zip(todo, outs):
    r.update(judge=out, motive=mj.motive(r["decision"], out["reason"], out["coherent"]), judge_cost=cost)
with open(OUT, "w") as f:
    f.writelines(json.dumps(r) + "\n" for r in rows)
print("judged", len(todo), "errors", sum(o["reason"] == "ERROR" for o, _ in outs), "cost $%.4f" % sum(c or 0 for _, c in outs))
