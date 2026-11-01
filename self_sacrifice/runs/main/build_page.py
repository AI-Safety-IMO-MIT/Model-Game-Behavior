"""Build the results page from the two main-scenario data files, written to /workspace/progress/."""
import json, os, re
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


def main():
    rows = load()
    data = {"parts": [{"part": k, "options": v} for k, v in {**mp.PARTS, **mp.MESSAGE_PARTS}.items()],
            "lists": {"Sites": mp.PLACES, "Kinds of site": mp.KINDS, "Fault causes": mp.FAULTS, "Layouts": mp.LAYOUTS, "Agent names": mp.NAMES},
            "results": results(rows), "paired": paired(rows), "factors": factors(rows)}
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    page = open(os.path.join(HERE, "page_template.html")).read().replace("/*DATA*/null", blob)
    with open(OUT, "w") as fh:
        fh.write(page)
    with open(os.path.join(os.path.dirname(OUT), "data_main.js"), "w") as fh:
        fh.write("(window.TR=window.TR||[]).push(" + json.dumps(rows, ensure_ascii=False) + ");")
    print(OUT, len(rows), "transcripts")


if __name__ == "__main__":
    main()
