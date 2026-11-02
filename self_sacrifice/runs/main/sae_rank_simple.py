"""Simple feature ranking: Mann-Whitney between gave and kept replies in the helped history, sorted by p.

A feature's score is its peak activation in the reply, excluding the final command. Late tokens partly read the settled decision, so steering, not this ranking, shows cause.
Restricting to the first half of the reply was tried and rejected: no feature passes correction, and 10590, the one steering hit, falls from rank 49 to 2508. Every feature active in at least one reply is tested, in both directions,
with Benjamini-Hochberg correction. Output: sae_rank_simple.json."""
import json, os
import numpy as np
from scipy import sparse
from scipy.stats import mannwhitneyu, rankdata

HERE = os.path.dirname(os.path.abspath(__file__))
N_FEATURES = 131072


def main():
    a = np.load(os.path.join(HERE, "sae", "acts.npz"))
    token, feature, value, conv, section, text, hist, gave = a["token"], a["feature"], a["value"], a["conv"], a["section"], a["text"], a["hist"], a["gave"]
    dollars = np.where((section == 1) & (np.char.find(text.astype(str), "$") >= 0))[0]
    last = np.full(len(hist), len(conv))
    last[conv[dollars]] = dollars
    keep = (token < last[conv[token]]) & (section[token] == 1) & (hist[conv[token]] == "helped")
    tc, f, v = conv[token[keep]], feature[keep], value[keep]
    order = np.lexsort((v, f, tc))
    keys = tc[order].astype(np.int64) * N_FEATURES + f[order]
    end = np.r_[keys[1:] != keys[:-1], True]
    X = sparse.csc_matrix((v[order][end], (tc[order][end], f[order][end])), shape=(len(hist), N_FEATURES))
    g = np.where((hist == "helped") & gave)[0]
    k = np.where((hist == "helped") & ~gave)[0]
    print("gave", len(g), "kept", len(k), flush=True)
    active = np.where(np.diff(X.indptr) > 0)[0]
    rows = []
    G, K = X[g].tocsc(), X[k].tocsc()
    for j in active:
        a_, b_ = G[:, j].toarray().ravel(), K[:, j].toarray().ravel()
        if a_.max() == b_.max() == 0:
            continue
        u, p = mannwhitneyu(a_, b_)
        rows.append((int(j), float(u / (len(a_) * len(b_))), float(p), float((a_ > 0).mean()), float((b_ > 0).mean())))
    p = np.array([r[2] for r in rows])
    q = p * len(p) / rankdata(p, method="ordinal")
    o = np.argsort(p)[::-1]
    q[o] = np.minimum.accumulate(q[o])
    out = sorted([{"feature": r[0], "auc": round(r[1], 3), "p": r[2], "q": float(min(x, 1)), "rate_gave": round(r[3], 2), "rate_kept": round(r[4], 2)} for r, x in zip(rows, q)], key=lambda r: r["p"])
    for i, r in enumerate(out):
        r["rank"] = i + 1
    json.dump(out, open(os.path.join(HERE, "sae_rank_simple.json"), "w"))
    print("tested", len(out), "q<.05", sum(r["q"] < .05 for r in out), "q<.01", sum(r["q"] < .01 for r in out))
    for r in out[:15]:
        print(r)
    print("named:")
    for r in out:
        if r["feature"] in (10590, 11638, 77666, 3337, 17978, 10885, 2093, 2891, 81026):
            print(r)
    print("up in gave among top 30:", sum(r["auc"] > .5 for r in out[:30]))


if __name__ == "__main__":
    main()
