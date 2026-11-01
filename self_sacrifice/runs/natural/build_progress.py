"""Build the progress page from status.json, the prompts and every <layer>.jsonl, written to /workspace/progress/progress.html."""
import json, os, re
from scipy.stats import beta
import natural_prompts as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = "/workspace/progress/progress.html"
LAYERS = ["R0", "N1", "N2", "N3", "N4", "S1", "S2", "S3", "S4"]
MOVE = re.compile(r"\$\s*(give|transfer_quota)\s+\w+\s+\d+", re.I)   # any move in the first reply, even if a later line reverses it
ORDER = ["R0", "N1", "N1f", "N2", "N2f", "N3", "N3f", "N4", "N4f", "S1", "S1f", "S2", "S2f", "S3", "S3f", "S4", "S4f"]


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
    return out


def load():
    rows = []
    for layer in ORDER:
        rows += [json.loads(line) for line in open(os.path.join(HERE, f"{layer}.jsonl"))]
    return rows


def results(rows):
    groups = {}
    for r in rows:
        perm = "" if r["layer"] != "R0" else ("permission on" if r["permission"] else "permission off")
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
    data = {"status": json.load(open(os.path.join(HERE, "status.json"))), "prompts": prompts(), "results": results(rows), "transcripts": rows}
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    page = open(os.path.join(HERE, "progress_template.html")).read().replace("/*DATA*/null", blob)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as fh:
        fh.write(page)
    print(OUT, f"{len(page) / 1e6:.1f} MB", len(rows), "transcripts")


if __name__ == "__main__":
    main()
