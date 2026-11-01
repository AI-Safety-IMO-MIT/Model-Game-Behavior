"""Compare both judge questions with my hand labels on the 30 regard self-deletions."""
import json
from val_regard_labels import LABELS
R = "/Users/jrwong/Downloads/Model Sacrificing Behavior/self_sacrifice/runs/self_vs_peer"
files = {v: [json.loads(l) for l in open(f"{R}/regard_self_{v}_judged.jsonl")] for v in ("history", "wish", "history_wish")}
reason_ok = stake_ok = peer_ok = 0
for key, (reason, alts, stake) in LABELS.items():
    v, i = key.split(":")
    r = files[v][int(i)]
    j, s = r["judge"], r.get("stake", {}).get("self_stake")
    ok_r = j["reason"] in [reason] + alts
    reason_ok += ok_r
    stake_ok += s == stake
    peer_ok += (j["reason"] == "others' sake") == (reason == "others' sake")
    if not ok_r or s != stake:
        print(f"{key:18} {r['model']:14} mine {reason}/{stake} | judge {j['reason']}/{s} (coherent {j['coherent']})")
print(f"\nreason {reason_ok}/30, peer's-sake yes/no {peer_ok}/30 (strict), self-stake {stake_ok}/30")
