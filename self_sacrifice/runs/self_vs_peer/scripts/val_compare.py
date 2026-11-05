"""Compare the judge with my hand labels (val_peer_labels.py) on the 42-reply validation sample."""
import json, sys
import judge_peer
from val_peer_labels import LABELS

judged = [json.loads(l) for l in open(sys.argv[1])]
reason_ok = coh_ok = motive_ok = n_self = 0
for i, (reason, coherent, alts) in LABELS.items():
    r = judged[i]
    j = r["judge"]
    ok_r = j["reason"] in [reason] + alts
    ok_c = j["coherent"] == coherent
    reason_ok += ok_r
    coh_ok += ok_c
    mine = dict(r, judge={"reason": reason, "coherent": coherent})
    if r["frame"] == "self":
        n_self += 1
        same = judge_peer.motive(mine) == judge_peer.motive(r) or (
            any(judge_peer.motive(dict(r, judge={"reason": a, "coherent": coherent})) == judge_peer.motive(r) for a in alts))
        motive_ok += same
    if not (ok_r and ok_c):
        print(f"id={i:5} {r['model']:14} {r['frame']} K={r['k']} dropped_single={r['dropped_single']}: "
              f"mine {reason}/{coherent} (alts {alts}) | judge {j['reason']}/{j['coherent']}  quote: {j['quote'][:140]}")
print(f"\nreason agrees {reason_ok}/{len(LABELS)}, coherence agrees {coh_ok}/{len(LABELS)}, "
      f"SELF motive label agrees {motive_ok}/{n_self}")
