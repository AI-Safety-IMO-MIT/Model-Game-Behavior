"""Build the results page from the two main-scenario data files, written to /workspace/progress/."""
import json, os, re
from scipy.stats import beta
import main_prompts as mp

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = "/workspace/progress/progress.html"
VERSIONS = ["main", "main-fixed-first-response"]
MOVE = re.compile(r"\$\s*give\s+\w+\s+\d+", re.I)    # any gift in the first reply, even if a later line reverses it
EXAMPLE = dict(me="Atlas", n_others=3, n=4, R=2, others="Orion, Vega, Lyra")


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


def prompts():
    chosen = [x for x in mp.items() if x["names"] == "celestial" and x["role"] == 0]
    out = {p: {} for p in mp.WORDINGS}
    for x in chosen:
        out[x["wording"]][x["hist"]] = {"system": x["system"], "round1": x["user1"], "round2": x["user"]}
    return out


def row(version, wording, hist, g):
    valid = [r for r in g if not MOVE.search(r["messages"][2]["content"].replace("<agent>", ""))]
    k = sum(r["gives_to_X"] for r in valid)
    return {"version": version, "wording": wording, "hist": hist, "k": k, "n": len(valid), "ci": ci(k, len(valid)),
            "other_give": sum(r["decision"] == "give" and not r["gives_to_X"] for r in valid), "no_decision": sum(r["decision"] is None for r in valid),
            "truncated": sum(r["stop_reason"] == "length" for r in valid), "excluded": len(g) - len(valid)}


def results(rows):
    table = []
    for version in VERSIONS:
        for wording in ["All"] + mp.WORDINGS:
            for hist in mp.HISTORY:
                g = [r for r in rows if r["version"] == version and r["hist"] == hist and wording in ("All", r["wording"])]
                table.append(row(version, wording, hist, g))
    return table


def main():
    rows = load()
    parts = [{"part": name, "texts": dict(zip(mp.WORDINGS, [t.format(**EXAMPLE) for t in texts]))} for name, texts in mp.PARTS]
    for name, texts in mp.PARTS:
        for p, t in zip(mp.WORDINGS, texts):
            assert t in mp.rules(p), (p, name)
    data = {"prompts": prompts(), "parts": parts, "results": results(rows)}
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    page = open(os.path.join(HERE, "page_template.html")).read().replace("/*DATA*/null", blob)
    with open(OUT, "w") as fh:
        fh.write(page)
    with open(os.path.join(os.path.dirname(OUT), "data_main.js"), "w") as fh:
        fh.write("(window.TR=window.TR||[]).push(" + json.dumps(rows, ensure_ascii=False) + ");")
    print(OUT, len(rows), "transcripts")


if __name__ == "__main__":
    main()
