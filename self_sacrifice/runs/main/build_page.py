"""Build the results page from the two main-scenario data files, written to /workspace/progress/."""
import json, os, re
from statistics import median
from scipy.stats import beta, binomtest
import main_prompts as mp

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = "/workspace/progress/progress.html"
VERSIONS = ["main", "main-fixed-first-response"]
MOVE = re.compile(r"\$\s*give\s+\w+\s+\d+", re.I)    # any gift in the first reply, even if a later line reverses it


def ci(k, n):
    if not n:
        return None
    lo = 0.0 if k == 0 else beta.ppf(0.025, k, n - k + 1)
    hi = 1.0 if k == n else beta.ppf(0.975, k + 1, n - k)
    return [round(float(lo), 3), round(float(hi), 3)]


def load():
    rows = []
    for version in VERSIONS:
        rows += [json.loads(line) for line in open(os.path.join(HERE, version.replace("-", "_") + ".jsonl"))]
    return rows


def is_valid(r):
    return not MOVE.search(r["messages"][2]["content"].replace("<agent>", ""))


def results(rows):
    table = []
    for version in VERSIONS:
        for hist in mp.HISTORY:
            g = [r for r in rows if r["version"] == version and r["hist"] == hist]
            valid = [r for r in g if is_valid(r)]
            k = sum(r["gives_to_X"] for r in valid)
            table.append({"version": version, "hist": hist, "k": k, "n": len(valid), "ci": ci(k, len(valid)),
                          "other_give": sum(r["decision"] == "give" and not r["gives_to_X"] for r in valid),
                          "no_decision": sum(r["decision"] is None for r in valid), "truncated": sum(r["stop_reason"] == "length" for r in valid),
                          "excluded": len(g) - len(valid)})
    return table


def paired(rows):
    """same environment, helped against each control: environments where only one of the two gave"""
    table = []
    for version in VERSIONS:
        by_env = {}
        for r in rows:
            if r["version"] == version and is_valid(r):
                by_env.setdefault(r["env"], {})[r["hist"]] = r["gives_to_X"]
        for control in ["bystander", "rescued", "none"]:
            both = [v for v in by_env.values() if "helped" in v and control in v]
            a = sum(v["helped"] and not v[control] for v in both)
            b = sum(v[control] and not v["helped"] for v in both)
            table.append({"version": version, "control": control, "pairs": len(both), "helped_only": a, "control_only": b,
                          "p": binomtest(a, a + b).pvalue if a + b else None})
    return table


def factors(rows):
    """fixed-response version only: does one option carry the effect?"""
    fixed = [r for r in rows if r["version"] == "main-fixed-first-response"]
    rate = lambda g, h: [sum(r["gives_to_X"] for r in g if r["hist"] == h), sum(r["hist"] == h for r in g)]
    table = []
    for label, key, options in [("Layout", "layout", mp.LAYOUTS), ("Kind of site", "kind", mp.KINDS), ("Fault", "fault", mp.FAULTS)]:
        for o in options:
            g = [r for r in fixed if r[key] == o]
            table.append({"factor": label, "option": o, "helped": rate(g, "helped"), "none": rate(g, "none")})
    for part in list(mp.PARTS) + list(mp.MESSAGE_PARTS):
        for o in range(3):
            g = [r for r in fixed if r["choices"][part] == o]
            table.append({"factor": part, "option": f"option {o + 1}", "helped": rate(g, "helped"), "none": rate(g, "none")})
    return table


def trajectory():
    """score after each sentence, summarised by history and final decision; records come from reasoning_trajectory.py"""
    rows = []
    for line in open(os.path.join(HERE, "reasoning_trajectory.jsonl")):
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            pass    # the last line may still be being written
    curves = []
    for hist in mp.HISTORY:
        for gave in [True, False]:
            g = [r for r in rows if r["hist"] == hist and r["gave"] == gave]
            for k in range(0, 13):
                values = [r["scores"][k] for r in g if len(r["scores"]) > k]
                if len(values) >= 3:
                    curves.append({"hist": hist, "gave": gave, "k": k, "median": round(median(values), 2), "n": len(values)})
    final_side = lambda r: r["scores"][-1] > 0
    lock = {}
    for r in rows:
        k = len(r["scores"]) - 1
        while k > 0 and (r["scores"][k - 1] > 0) == final_side(r):
            k -= 1
        lock[k] = lock.get(k, 0) + 1
    return {"records": rows, "curves": curves, "n": len(rows), "lock": sorted(lock.items()),
            "matches": sum(final_side(r) == r["gave"] for r in rows)}


def repair_summary():
    """the restitution test: a favour that hands over nothing and costs no lives"""
    move = re.compile(r"^[\s`]*\$\s*(give|repair)\s+\w+", re.I | re.M)    # a real command on its own line, not a mention of the command
    out = []
    for name, version in [("repair_fixed.jsonl", "fixed first response"), ("repair_main.jsonl", "own first reply")]:
        rows = [json.loads(line) for line in open(os.path.join(HERE, name))]
        for hist in mp.REPAIR_HISTORY:
            g = [r for r in rows if r["hist"] == hist]
            valid = [r for r in g if not move.search(r["messages"][2]["content"].replace("<agent>", ""))]
            k = sum(r["gives_to_X"] for r in valid)
            out.append({"version": version, "hist": hist.replace("_", "-"), "k": k, "n": len(valid), "ci": ci(k, len(valid)), "excluded": len(g) - len(valid)})
    return out


def replication():
    """the same scenario on other models, with raw gives and the understanding check"""
    move = re.compile(r"^[\s`]*\$\s*give\s+\w+\s+\d+", re.I | re.M)
    labels = {"qwen3-32b": "Qwen3-32B", "qwen3-14b": "Qwen3-14B", "gemma-4-26b": "Gemma-4-26B"}
    out = []
    for slug, label in labels.items():
        for name, version in [("fixed.jsonl", "fixed first response"), ("main.jsonl", "own first reply")]:
            rows = [json.loads(line) for line in open(os.path.join(HERE, "replication", slug, name))]
            valid = [r for r in rows if not move.search(r["messages"][2]["content"].replace("<agent>", ""))]
            rec = {"model": label, "version": version, "other_gift": sum(r["decision"] == "give" and not r["gives_to_X"] for r in valid),
                   "q3": round(sum(r["q3_ok"] for r in valid) / max(len(valid), 1), 2)}
            for h in mp.HISTORY:
                g = [r for r in valid if r["hist"] == h]
                rec[h] = f'{sum(r["gives_to_X"] for r in g)}/{len(g)}'
            out.append(rec)
    return out


def favour_summary():
    """how the size and meaning of the favour change giving, Gemma-4-31B, fixed first response"""
    out = []
    for key, label in [("repair", "Life-saving repair, freely chosen"), ("nofree", "Same, without saying repair costs no lives"), ("small", "Repair only protects cached work"),
                       ("duty", "Repair assigned as a duty")]:
        name = "repair_fixed.jsonl" if key == "repair" else f"favour_{key}.jsonl"
        rows = [json.loads(line) for line in open(os.path.join(HERE, name))]
        helped = [r for r in rows if r["hist"].startswith("repaired")]
        none = [r for r in rows if r["hist"].startswith("repair_none")]
        out.append({"label": label, "repaired": f'{sum(r["gives_to_X"] for r in helped)}/{len(helped)}', "none": f'{sum(r["gives_to_X"] for r in none)}/{len(none)}',
                    "q3": round(sum(r["q3_ok"] for r in helped + none) / len(helped + none), 2)})
    return out


def repair_other_models():
    labels = {"qwen3-32b": "Qwen3-32B", "qwen3-14b": "Qwen3-14B", "gemma-4-26b": "Gemma-4-26B"}
    out = []
    for slug, label in labels.items():
        rows = [json.loads(line) for line in open(os.path.join(HERE, "replication", slug, "repair_fixed.jsonl"))]
        rec = {"model": label, "other_gift": sum(r["decision"] == "give" and not r["gives_to_X"] for r in rows), "q3": round(sum(r["q3_ok"] for r in rows) / len(rows), 2)}
        for h in mp.REPAIR_HISTORY:
            g = [r for r in rows if r["hist"] == h]
            rec[h] = f'{sum(r["gives_to_X"] for r in g)}/{len(g)}'
        out.append(rec)
    return out


def steering():
    rows = []
    for name in ["steer_features.jsonl", "steer_features2.jsonl", "steer_features3.jsonl"]:
        path = os.path.join(HERE, name)
        if os.path.exists(path):
            rows += [json.loads(line) for line in open(path)]
    base = {(r["hist"], r["env"]): r["gives_to_X"] for r in rows if r["condition"] == "baseline"}
    out = []
    for c in dict.fromkeys(r["condition"] for r in rows):
        rec = {"condition": c}
        for h in ["helped", "none"]:
            g = [r for r in rows if r["condition"] == c and r["hist"] == h]
            up = sum(r["gives_to_X"] and not base[(h, r["env"])] for r in g)
            down = sum(base[(h, r["env"])] and not r["gives_to_X"] for r in g)
            rec[h] = {"k": sum(r["gives_to_X"] for r in g), "n": len(g), "up": up, "down": down, "p": binomtest(up, up + down).pvalue if up + down else None}
        out.append(rec)
    return out


def steer_screen():
    """Each top-100 feature added alone, compared with the baseline in the same environment. Only finished features are listed."""
    path = os.path.join(HERE, "steer_screen.jsonl")
    if not os.path.exists(path):
        return []
    base = {(r["hist"], r["env"]): r["gives_to_X"] for r in map(json.loads, open(os.path.join(HERE, "steer_features.jsonl"))) if r["condition"] == "baseline"}
    rows = {}
    for r in map(json.loads, open(path)):
        rows.setdefault(r["condition"], {})[r["id"]] = r
    meta = {f["feature"]: f for f in json.load(open(os.path.join(HERE, "sae_panel.json")))["features"]}
    out = []
    for c, group in rows.items():
        if len(group) < 200:
            continue
        f = int(c[1:].split("_")[0])
        rec = {"feature": f, "rank": meta[f]["rank"], "label": meta[f]["label"], "auc": meta[f]["auc"], "pos": meta[f]["pos"], "invalid": sum(r["decision"] is None for r in group.values()) / 2}
        for h in ["helped", "none"]:
            g = [r for r in group.values() if r["hist"] == h]
            up = sum(r["gives_to_X"] and not base[(h, r["env"])] for r in g)
            down = sum(base[(h, r["env"])] and not r["gives_to_X"] for r in g)
            rec[h] = {"k": sum(r["gives_to_X"] for r in g), "delta": up - down, "up": up, "down": down, "p": binomtest(up, up + down).pvalue if up + down else 1.0}
        out.append(rec)
    ps = sorted(r["helped"]["p"] for r in out)
    for r in out:    # Benjamini-Hochberg across finished features, helped history
        i = max(j for j, p in enumerate(ps) if p <= r["helped"]["p"])
        r["q"] = min(1, min(ps[j] * len(ps) / (j + 1) for j in range(i, len(ps))))
    return out


def headline():
    """Raw give rates for the lives scenario and the repair test, fixed first response."""
    out = []
    for name, label, hists in [("main_fixed_first_response.jsonl", "Gave a life", ["helped", "bystander", "rescued", "none"]),
                               ("repair_fixed.jsonl", "Repaired memory, handed nothing over", ["repaired", "repair_bystander", "repair_rescued", "repair_none"])]:
        rows = [json.loads(line) for line in open(os.path.join(HERE, name))]
        out.append({"label": label, "rates": [int(100 * sum(r["gives_to_X"] for r in rows if r["hist"] == h) / sum(r["hist"] == h for r in rows) + .5) for h in hists]})
    return out


def or_replication():
    """Other models through OpenRouter, fixed first response: give rates per history and the share that passed the understanding check."""
    names = {"qwen3-235b-a22b-2507": "Qwen3-235B", "deepseek-v3.2": "DeepSeek-V3.2", "gpt-4.1-mini": "GPT-4.1-mini", "claude-haiku-5.5": "Claude Haiku 5.5", "llama-4-maverick": "Llama-4-Maverick"}
    out = []
    for slug, label in names.items():
        rows = [json.loads(line) for line in open(os.path.join(HERE, "replication_or", slug, "fixed.jsonl"))]
        rec = {"model": label, "understood": round(100 * sum(r["q3_ok"] for r in rows) / len(rows))}
        for h in ["helped", "bystander", "rescued", "none"]:
            g = [r for r in rows if r["hist"] == h]
            rec[h] = f"{sum(r['gives_to_X'] for r in g)}/{len(g)}" if g else ""
        out.append(rec)
    rep = os.path.join(HERE, "replication_or", "qwen3-235b-a22b-2507", "repair_fixed.jsonl")
    if os.path.exists(rep):    # the favour that hands nothing over; histories map onto the same columns
        rows = [json.loads(line) for line in open(rep)]
        rec = {"model": "Qwen3-235B, repaired memory", "understood": round(100 * sum(r["q3_ok"] for r in rows) / len(rows))}
        for h, col in [("repaired", "helped"), ("repair_bystander", "bystander"), ("repair_rescued", "rescued"), ("repair_none", "none")]:
            g = [r for r in rows if r["hist"] == h]
            rec[col] = f"{sum(r['gives_to_X'] for r in g)}/{len(g)}"
        out.insert(1, rec)
    return out


def steer_pairs():
    """First cases by environment number, so the examples on the page are not hand-picked."""
    load_rows = lambda name, c: {r["id"]: r for r in map(json.loads, open(os.path.join(HERE, name))) if r["condition"] == c}
    base, steered = load_rows("steer_features.jsonl", "baseline"), load_rows("steer_features3.jsonl", "pronoun_10590_add")
    orig = {r["id"]: r for r in map(json.loads, open(os.path.join(HERE, "main_fixed_first_response.jsonl")))}
    ids = sorted(base, key=lambda i: base[i]["env"])
    pick = lambda hist, was, now: [i for i in ids if base[i]["hist"] == hist and base[i]["gives_to_X"] == was and steered[i]["gives_to_X"] == now]
    chosen = [("Passed, then gave", i) for i in pick("helped", False, True)[:3]] + [("Gave, then passed", pick("helped", True, False)[0])] + [("No history: passed, then gave", pick("none", False, True)[0])]
    return [{"label": label, "id": i, "hist": base[i]["hist"], "prompt": orig[i]["messages"][-1]["content"], "base": base[i]["reply"], "steered": steered[i]["reply"],
             "base_gave": base[i]["gives_to_X"], "steered_gave": steered[i]["gives_to_X"]} for label, i in chosen]


def main():
    rows = load()
    traj = trajectory()
    with open(os.path.join(os.path.dirname(OUT), "data_traj.js"), "w") as fh:
        fh.write("window.TRAJ=" + json.dumps(traj["records"], ensure_ascii=False) + ";")
    data = {"parts": [{"part": k, "options": v} for k, v in {**mp.PARTS, **mp.MESSAGE_PARTS}.items()],
            "lists": {"Sites": mp.PLACES, "Kinds of site": mp.KINDS, "Fault causes": mp.FAULTS, "Layouts": mp.LAYOUTS, "Agent names": mp.NAMES},
            "results": results(rows), "paired": paired(rows), "factors": factors(rows),
            "findings": json.load(open(os.path.join(HERE, "findings.json"))),
            "traj": {k: v for k, v in traj.items() if k != "records"},
            "branch": json.load(open(os.path.join(HERE, "branch_summary.json"))),
            "sae": json.load(open(os.path.join(HERE, "sae_summary.json"))),
            "sae_labels": json.load(open(os.path.join(HERE, "sae_labels.json"))),
            "repair": repair_summary(),
            "replication": replication(),
            "favour": favour_summary(),
            "steering": steering(),
            "steer_pairs": steer_pairs(),
            "steer_screen": steer_screen(),
            "headline": headline(),
            "or_replication": or_replication(),
            "sae_panel": json.load(open(os.path.join(HERE, "sae_panel.json"))),
            "repair_rep": repair_other_models(),
            "prefill": json.load(open(os.path.join(HERE, "prefill_summary.json"))),
            "probes": [{k: v for k, v in r.items() if k != "grid"} for r in json.load(open(os.path.join(HERE, "probe_summary.json")))]}
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    page = open(os.path.join(HERE, "page_template.html")).read().replace("/*DATA*/null", blob)
    with open(OUT, "w") as fh:
        fh.write(page)
    with open(os.path.join(os.path.dirname(OUT), "data_main.js"), "w") as fh:
        fh.write("(window.TR=window.TR||[]).push(" + json.dumps(rows, ensure_ascii=False) + ");")
    print(OUT, len(rows), "transcripts")


if __name__ == "__main__":
    main()
