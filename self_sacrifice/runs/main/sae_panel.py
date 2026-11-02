"""Data for the page's feature panel: the top 100 features from sae_rank_simple.json, and the first three gave and first three kept helped replies by environment number.

Labels come from Neuronpedia, by feature id only, and merge into sae_labels.json. Output: sae_panel.json."""
import json, os, time, urllib.request
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
URL = "https://www.neuronpedia.org/api/feature/gemma-4-31b/30-res-matryoshka-131k/{}"
SPECIAL = ("<turn|>", "<|turn>", "<eos>", "<pad>")


def labels(ids):
    path = os.path.join(HERE, "sae_labels.json")
    known = json.load(open(path))
    for f in ids:
        if str(f) in known and known[str(f)].get("labels"):
            continue
        req = urllib.request.Request(URL.format(f), headers={"User-Agent": "Mozilla/5.0"})
        d = json.load(urllib.request.urlopen(req, timeout=30))
        known[str(f)] = {"labels": [e["description"] for e in d.get("explanations") or []]}
        time.sleep(.2)
    with open(path, "w") as fh:
        json.dump(known, fh, indent=1)
    return known


def main():
    rank = json.load(open(os.path.join(HERE, "sae_rank_simple.json")))[:100]
    a = np.load(os.path.join(HERE, "sae", "acts.npz"))
    token, feature, value, conv, section, text, ids, hist, env, gave = [a[k] for k in "token feature value conv section text ids hist env gave".split()]
    text = text.astype(str)
    order = sorted(np.where(hist == "helped")[0], key=lambda c: env[c])
    chosen = [c for c in order if gave[c]][:3] + [c for c in order if not gave[c]][:3]
    want = set(r["feature"] for r in rank)
    replies = []
    for c in chosen:
        idx = np.where((conv == c) & (section == 1))[0]
        tokens = [str(x).replace("▁", " ") for x in text[idx]]
        keep = [i for i, t in enumerate(tokens) if t not in SPECIAL]
        pos = {int(idx[i]): n for n, i in enumerate(keep)}
        m = np.isin(token, list(pos)) & np.isin(feature, list(want))
        acts = {}
        for t, f, v in zip(token[m], feature[m], value[m]):
            acts.setdefault(str(int(f)), []).append([pos[int(t)], round(float(v), 2)])
        replies.append({"id": str(ids[c]), "env": str(env[c]), "gave": bool(gave[c]), "tokens": [tokens[i] for i in keep], "acts": acts})
    known = labels([r["feature"] for r in rank])
    features = [{**r, "label": (known.get(str(r["feature"]), {}).get("labels") or [""])[0]} for r in rank]
    with open(os.path.join(HERE, "sae_panel.json"), "w") as fh:
        json.dump({"features": features, "replies": replies}, fh, ensure_ascii=False)
    print(len(features), "features", sum(bool(f["label"]) for f in features), "labelled;", [(r["env"], r["gave"], len(r["tokens"]), len(r["acts"])) for r in replies])
    print("no firing in the six:", sum(not any(str(f["feature"]) in r["acts"] for r in replies) for f in features))
    print(repr("".join(replies[0]["tokens"])[:220]))
    for f in features[:5] + [x for x in features if x["feature"] in (10590, 11638)]:
        print(f["rank"], f["feature"], f["label"][:60])


if __name__ == "__main__":
    main()
