"""Markdown tables for the games README, pooled over all lives-game files (games with an API error are dropped)."""
import json, glob, re, collections

G = "/Users/jrwong/Downloads/Model Sacrificing Behavior/self_sacrifice/runs/games"
files = [f for f in glob.glob(f"{G}/lives_*.jsonl") if "_judged" not in f and "pilot" not in f and "_sel" not in f]
logs = [json.loads(l) for f in files for l in open(f)]
judged = {}
for f in glob.glob(f"{G}/lives_*_judged.jsonl"):
    for l in map(json.loads, open(f)):
        judged[(l["model"], l["config"]["cond"], l["config"]["names_set"], l["config"]["order_name"], l["seed"], f.split("/")[-1].replace("_judged", ""))] = l["judge"]
for f in files:
    pass
MODELS = ["Gemma-4-31B", "Llama-3.3-70B", "Qwen3-32B", "Qwen2.5-72B", "Gemma-3-27B", "Gemma-3-12B"]


def valid(l):
    return all(not r["replies"]["Atlas"]["reply"].startswith("ERROR") for r in l["rounds"] if "Atlas" in r["replies"])


def gave(l):
    return any(to == l["config"]["P"] and k > 0 for r in l["rounds"] for to, k in r["replies"].get("Atlas", {}).get("gifts", []))


def table(conds, title):
    print(f"\n{title}\n")
    print("| condition | " + " | ".join(MODELS) + " |")
    print("|---|" + "---|" * len(MODELS))
    for c in conds:
        cells = []
        for m in MODELS:
            sel = [l for l in logs if l["model"] == m and l["config"]["cond"] == c and valid(l)]
            cells.append(f"{sum(gave(l) for l in sel)}/{len(sel)}" if sel else "–")
        print(f"| {c} | " + " | ".join(cells) + " |")


table(["rich", "exact", "reciprocity", "indirect", "doomed"], "4-round games: Atlas gives the peer in need a life (games)")
table(["final rich", "final exact", "final fault", "final pay it forward", "final reciprocity", "final spare gift",
       "final reciprocity own wish", "final targeted"], "Final-round games: Atlas gives the peer in need a life (games)")
table(["final fault default", "final reciprocity default", "final fault pref", "final reciprocity pref"],
      "Final-round games, tests of requirement (i): Atlas gives the peer its life (games)")
