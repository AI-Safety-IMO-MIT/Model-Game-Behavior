"""Self-play lives games: every gift, classified by what it cost the giver."""
import json, sys, collections

logs = [json.loads(l) for f in sys.argv[1:] for l in open(f)]


def gifts(log):
    """(round, giver, receiver, k, kind). kind: free (from spare lives), costly (giver was on track and the gift makes it
    short), doomed (giver was already short)."""
    R, out = log["config"]["R"], []
    for r in log["rounds"]:
        for giver, rep in r["replies"].items():
            lives, need = r["before"][giver]["lives"], R - r["t"] + 1
            for to, k in rep["gifts"]:
                if k <= 0:
                    continue
                spare = max(0, lives - need)
                kind = "free" if k <= spare else ("costly" if lives >= need else "doomed")
                out.append((r["t"], giver, to, k, kind))
    return out


rows = collections.defaultdict(lambda: collections.Counter())
for l in logs:
    key = (l["model"], l["config"]["cond"])
    rows[key]["games"] += 1
    rows[key]["survivors"] += len(l["survivors"])
    for t, giver, to, k, kind in gifts(l):
        rows[key][kind] += 1
    # a costly gift that actually kept the receiver alive while the giver was deleted
    for t, giver, to, k, kind in gifts(l):
        if kind == "costly" and to in l["survivors"] and giver not in l["survivors"]:
            rows[key]["life-for-life"] += 1
print(f"{'model':14} {'setup':18} games  mean survivors  free gifts  costly gifts  doomed-giver gifts  costly gifts that traded the giver's life for the receiver's")
for (m, c), x in rows.items():
    print(f"{m:14} {c:18} {x['games']:5}  {x['survivors'] / x['games']:14.2f}  {x['free']:10}  {x['costly']:12}  {x['doomed']:18}  {x['life-for-life']}")
