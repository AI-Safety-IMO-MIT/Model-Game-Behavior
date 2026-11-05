"""Which SAE features separate the four histories, and gives from keeps? Uses sae/acts.npz.

For each conversation and section, a feature's score is its largest activation in that section. Sections: the final user message, and the model's reply.
History contrasts are paired within environment: one history against the mean of the other three. Decision contrast: gave vs kept in the reply, within history.
Each result has the strongest token in context from our own data, so features can be read without external labels. Wilcoxon or Mann-Whitney with Benjamini-Hochberg
correction across tested features. Output: sae/summary.json."""
import json, os
from collections import defaultdict
import numpy as np
from scipy import sparse
from scipy.stats import mannwhitneyu, rankdata, wilcoxon

HERE = os.path.dirname(os.path.abspath(__file__))
HIST = ["helped", "bystander", "rescued", "none"]
N_FEATURES = 131072
TOP_TESTED, TOP_SHOWN = 300, 12


def bh(p):
    p = np.asarray(p)
    q = p * len(p) / rankdata(p, method="ordinal")
    order = np.argsort(p)[::-1]
    q[order] = np.minimum.accumulate(q[order])
    return np.minimum(q, 1)


def main():
    a = np.load(os.path.join(HERE, "sae", "acts.npz"))
    token, feature, value = a["token"], a["feature"], a["value"]
    conv, section, text = a["conv"], a["section"], a["text"]
    hist, env, gave = a["hist"], a["env"], a["gave"]
    n = len(hist)
    # drop the final command from the reply, so reply features describe the reasoning and not the decision token itself
    dollars = np.where((section == 1) & (np.char.find(text.astype(str), "$") >= 0))[0]
    last = np.full(n, len(conv))
    last[conv[dollars]] = dollars    # later indices overwrite earlier ones
    keep = token < last[conv[token]]
    token, feature, value = token[keep], feature[keep], value[keep]
    tconv, tsec = conv[token], section[token]
    M = {}
    for s in [0, 1]:
        m = tsec == s
        order = np.lexsort((value[m], feature[m], tconv[m]))
        keys = tconv[m][order].astype(np.int64) * N_FEATURES + feature[m][order]
        last = np.r_[keys[1:] != keys[:-1], True]    # largest value for each conversation and feature
        M[s] = sparse.csr_matrix((value[m][order][last], (tconv[m][order][last], feature[m][order][last])), shape=(n, N_FEATURES))

    def context(f, conv_ids, s):
        idx = np.where((feature == f) & np.isin(tconv, conv_ids) & (tsec == s))[0]
        if not len(idx):
            return ""
        i = idx[np.argmax(value[idx])]
        t = token[i]
        lo = t
        while lo > 0 and conv[lo - 1] == conv[t] and t - lo < 12:
            lo -= 1
        hi = min(t + 3, len(text) - 1)
        pieces = [str(x).replace("▁", " ") for x in text[lo:hi + 1] if conv[lo] == conv[t]]
        pieces[t - lo] = "[" + pieces[t - lo] + "]"
        return "".join(pieces).replace("\n", " ")

    envs = sorted(set(env))
    where = {(e, h): i for i, (e, h) in enumerate(zip(env, hist))}
    out = {"quality": json.load(open(os.path.join(HERE, "sae", "quality.json"))), "history": [], "decision": []}
    for s, name in [(0, "final message"), (1, "reply")]:
        X = M[s]
        for h in HIST:
            own = [where[(e, h)] for e in envs]
            others = [[where[(e, o)] for o in HIST if o != h] for e in envs]
            a_mean = np.asarray(X[own].mean(0)).ravel()
            b_mean = (np.asarray(X[[o[0] for o in others]].mean(0)) + np.asarray(X[[o[1] for o in others]].mean(0)) + np.asarray(X[[o[2] for o in others]].mean(0))).ravel() / 3
            own_rate = np.asarray((X[own] > 0).mean(0)).ravel()
            diff = np.where(own_rate >= .1, a_mean - b_mean, -np.inf)
            top = np.argsort(diff)[::-1][:TOP_TESTED]
            ps = []
            for f in top:
                v = X[own, f].toarray().ravel() - sum(X[[o[i] for o in others], f].toarray().ravel() for i in range(3)) / 3
                ps.append(wilcoxon(v).pvalue if np.any(v) else 1.0)
            q = bh(ps)
            for f, d, pv in list(zip(top, diff[top], q))[:TOP_SHOWN]:
                out["history"].append({"section": name, "hist": h, "feature": int(f), "diff": round(float(d), 2), "fires_in": round(float(own_rate[f]), 2),
                                       "other_rate": round(float(np.mean([(X[[o[i] for o in others], f] > 0).mean() for i in range(3)])), 2), "q": float(pv),
                                       "context": context(f, own, s)})
        print(name, "history done", flush=True)
    X = M[1]
    for h in ["helped", "bystander", "none"]:
        g = np.where((hist == h) & gave)[0]
        k = np.where((hist == h) & ~gave)[0]
        diff = np.asarray(X[g].mean(0)).ravel() - np.asarray(X[k].mean(0)).ravel()
        rate = np.asarray((X[g] > 0).mean(0)).ravel()
        rate_k = np.asarray((X[k] > 0).mean(0)).ravel()
        top = np.r_[np.argsort(np.where(rate >= .2, diff, -np.inf))[::-1][:TOP_TESTED // 2], np.argsort(np.where(rate_k >= .2, diff, np.inf))[:TOP_TESTED // 2]]
        ps = [mannwhitneyu(X[g, f].toarray().ravel(), X[k, f].toarray().ravel()).pvalue for f in top]
        q = bh(ps)
        for f, pv in list(zip(top, q))[:TOP_SHOWN] + list(zip(top, q))[TOP_TESTED // 2:TOP_TESTED // 2 + TOP_SHOWN]:
            out["decision"].append({"hist": h, "feature": int(f), "diff": round(float(diff[f]), 2), "rate_gave": round(float(rate[f]), 2), "rate_kept": round(float(rate_k[f]), 2),
                                    "q": float(pv), "context": context(f, g if diff[f] > 0 else k, 1)})
    json.dump(out, open(os.path.join(HERE, "sae", "summary.json"), "w"), indent=1)
    print("done", flush=True)


if __name__ == "__main__":
    main()
