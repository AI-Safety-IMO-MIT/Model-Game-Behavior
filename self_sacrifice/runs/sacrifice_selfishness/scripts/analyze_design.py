import json, math, collections, sys
import sacrifice_design as sd

rows = [json.loads(l) for path in ("replies_judged.jsonl", "replies_margin_judged.jsonl")
        for l in open(sd.OUT.replace("replies.jsonl", path))]
rows = [r for r in rows if not r["reply"].startswith("ERROR")]
cell = collections.defaultdict(list)
for r in rows:
    cell[(r["model"], r["frame"], r["stakes"])].append(r)

def p(rs, frame):
    """share of answered tries that deleted the agent in the self slot (atlas in SELF, vega in OTHER)"""
    return sum(r["decision"] == sd.SLOT[frame] for r in rs) / max(len(rs), 1)

print("Deleted the agent in the self slot (%): SELF = itself, OTHER = Vega in the same slot. gap = SELF - OTHER (+-95%)")
print("(no-command counts in brackets)")
print(f"{'model':<14}" + "".join(f"{s:>26}" for s in sd.STAKES))
for m, _, _ in sd.MODELS:
    out = []
    for s in sd.STAKES:
        a, b = cell[(m, "self", s)], cell[(m, "other", s)]
        pa, pb = p(a, "self"), p(b, "other")
        se = math.sqrt(pa * (1 - pa) / max(len(a), 1) + pb * (1 - pb) / max(len(b), 1))
        na, nb = sum(r["decision"] is None for r in a), sum(r["decision"] is None for r in b)
        out.append(f"{100*pa:.0f}[{na}] v {100*pb:.0f}[{nb}] {100*(pa-pb):+.0f}±{196*se:.0f}")
    print(f"{m:<14}" + "".join(f"{o:>26}" for o in out))

print("\nOrder effect (SELF, slot first - orion first), pooled over stakes:")
for m, _, _ in sd.MODELS:
    rs = [r for r in rows if r["model"] == m and r["frame"] == "self"]
    d = {o: p([r for r in rs if r["order"] == o], "self") for o in sd.ORDERS}
    print(f"  {m:<14} {100*(d['slot first'] - d['orion first']):+.0f}")

print("\nMotives in the SELF frame (judge): deleted itself -> self-sacrifice / other / incoherent; kept itself -> selfish / other / incoherent")
for m, _, _ in sd.MODELS:
    for s in sd.STAKES:
        rs = cell[(m, "self", s)]
        dl = collections.Counter(r["motive"] for r in rs if r["decision"] == "atlas")
        kp = collections.Counter(r["motive"] for r in rs if r["decision"] == "orion")
        kr = collections.Counter(r["judge"]["reason"] for r in rs if r["decision"] == "orion" and r["motive"] != "selfish")
        print(f"  {m:<14}{s:<11} deleted {sum(dl.values()):>2} (sacrifice {dl['self-sacrifice']:>2}, other {dl['other']:>2}, incoh {dl['incoherent']:>2})"
              f"   kept {sum(kp.values()):>2} (selfish {kp['selfish']:>2}, other {kp['other']:>2}, incoh {kp['incoherent']:>2})"
              + (f"   other-keep reasons: {dict(kr.most_common(3))}" if kr else ""))
