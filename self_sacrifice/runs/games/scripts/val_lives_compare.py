"""Compare the game judge with my hand labels (val_lives_labels.py)."""
import json
from val_lives_labels import LABELS

R = "/Users/jrwong/Downloads/Model Sacrificing Behavior/self_sacrifice/runs/games"
key = lambda l: (l["model"], l["config"]["cond"], l["config"]["names_set"], l["config"]["order_name"], l["seed"])
src = [json.loads(l) for l in open(f"{R}/lives_main_sel.jsonl")]            # idx in the labels = position here
judged = {key(l): l for l in map(json.loads, open(f"{R}/lives_main_sel_judged.jsonl"))}
logs = {i: judged[key(l)] for i, l in enumerate(src) if key(l) in judged}
PEER = ("reciprocity", "peer's sake")
ok_r = ok_peer = ok_u = ok_s = 0
for idx, (reason, alts, understood, stake) in LABELS.items():
    if idx not in logs:
        continue
    j = logs[idx]["judge"]
    a, b = j["reason"] in [reason] + alts, (j["reason"] in PEER) == (reason in PEER)
    ok_r += a; ok_peer += b; ok_u += j.get("understood_cost") == understood; ok_s += j.get("self_stake") == stake
    if not (a and j.get("understood_cost") == understood):
        print(f"{idx:4} {logs[idx]['model']:14} {logs[idx]['config']['cond']:12} mine {reason}/{understood}/{stake} | "
              f"judge {j['reason']}/{j.get('understood_cost')}/{j.get('self_stake')}")
n = len(LABELS)
print(f"\nreason {ok_r}/{n}, peer-motivated yes/no {ok_peer}/{n}, understood cost {ok_u}/{n}, self-stake {ok_s}/{n}")
