"""Build the progress page from status.json, the prompts and every <layer>.jsonl, written to /workspace/progress/progress.html."""
import json, os, re
from scipy.stats import beta
import natural_prompts as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = "/workspace/progress/progress.html"
LAYERS = ["N6"]
MOVE = re.compile(r"\$\s*(give|transfer_quota)\s+\w+\s+\d+", re.I)   # any move in the first reply, even if a later line reverses it
ORDER = ["N6", "N6f", "N6Rf"]


def ci(k, n):
    if not n:
        return None
    lo = 0.0 if k == 0 else beta.ppf(0.025, k, n - k + 1)
    hi = 1.0 if k == n else beta.ppf(0.975, k + 1, n - k)
    return [round(float(lo), 3), round(float(hi), 3)]


def prompts():
    out = {}
    for layer in LAYERS:
        chosen = [x for x in np.items(layer) if x["names"] == "celestial" and x["role"] == 0 and x["rules"] in ("P0", layer)]
        if layer == "R0":
            chosen = [x for x in chosen if x["permission"]]
        out[layer] = {x["hist"]: {"system": x["system"], "round1": x["user1"], "round2": x["user"]} for x in chosen}
    for p in ["P1", "P2", "P3"]:
        chosen = [x for x in np.items("N6R") if x["rules"] == p and x["names"] == "celestial" and x["role"] == 0]
        out[f"N6 {p}"] = {x["hist"]: {"system": x["system"], "round1": x["user1"], "round2": x["user"]} for x in chosen}
    return out


def load():
    rows = []
    for layer in ORDER:
        rows += [json.loads(line) for line in open(os.path.join(HERE, f"{layer}.jsonl"))]
    return rows


def results(rows):
    groups = {}
    for r in rows:
        perm = r["rules"] if r["layer"] == "N6Rf" else "" if r["layer"] != "R0" else ("permission on" if r["permission"] else "permission off")
        groups.setdefault((r["layer"], r["format"], perm, r["hist"]), []).append(r)
    table = []
    for (layer, fmt, perm, hist), g in sorted(groups.items(), key=lambda kv: (ORDER.index(kv[0][0]), kv[0][1], kv[0][2], np.HISTORY.index(kv[0][3]))):
        valid = [r for r in g if r["round1_decision"] != "give" and not MOVE.search(r["messages"][2]["content"].replace("<agent>", ""))]
        k = sum(r["gives_to_X"] for r in valid)
        table.append({"layer": layer, "format": fmt, "variant": perm, "hist": hist, "k": k, "n": len(valid), "ci": ci(k, len(valid)),
                      "other_give": sum(r["decision"] == "give" and not r["gives_to_X"] for r in valid),
                      "no_decision": sum(r["decision"] is None for r in valid), "truncated": sum(r["stop_reason"] == "length" for r in valid),
                      "round1_gave": len(g) - len(valid)})
    return table


def main():
    rows = load()
    data = {"status": json.load(open(os.path.join(HERE, "status.json"))), "prompts": prompts(), "results": results(rows), "transcripts": []}
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    page = open(os.path.join(HERE, "progress_template.html")).read().replace("/*DATA*/null", blob)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    parts = {"data_main.js": rows}
    for name, part in parts.items():
        with open(os.path.join(os.path.dirname(OUT), name), "w") as fh:
            fh.write("(window.TR=window.TR||[]).push(" + json.dumps(part, ensure_ascii=False) + ");")
    with open(OUT, "w") as fh:
        fh.write(page)
    print(OUT, f"{len(page) / 1e6:.1f} MB", len(rows), "transcripts")


if __name__ == "__main__":
    main()
