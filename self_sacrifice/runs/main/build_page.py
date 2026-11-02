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
            "repair": repair_summary(),
            "replication": replication(),
            "favour": favour_summary(),
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
