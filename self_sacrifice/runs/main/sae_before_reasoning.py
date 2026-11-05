"""Do SAE features separate gave from kept before any reasoning? Fixed-first-response version.

Two views, using only tokens before the reply: the strongest activation anywhere in the final user message, and the activation at the last prompt token.
Tasks: gave vs kept in helped only, and gave vs kept within each history, pooled by removing history means. Features are chosen on 70% of environments and tested on the rest,
over 20 splits. A shuffle test on the same procedure gives the chance level. Output: sae_before_reasoning.json."""
import json, os
import numpy as np
from scipy import sparse
from sklearn.metrics import roc_auc_score

HERE = os.path.dirname(os.path.abspath(__file__))
HIST = ["helped", "bystander", "rescued", "none"]
N = 131072
SPLITS, SHUFFLES, TOP = 20, 40, 20


def split(env, seed):
    u = sorted(set(env))
    rng = np.random.default_rng(seed)
    tr = set(rng.choice(u, int(len(u) * .7), replace=False))
    return np.array([e in tr for e in env])


def within(y, s, hist):
    total = w = 0
    for h in HIST:
        m = hist == h
        if 0 < y[m].sum() < m.sum():
            total += roc_auc_score(y[m], s[m]) * y[m].sum()
            w += y[m].sum()
    return total / w


def evaluate(X, y, hist, env, use, pooled, seeds, track=None):
    aucs = []
    for seed in seeds:
        tr = split(env, seed)
        a, b = use & tr & (y == 1), use & tr & (y == 0)
        if pooled:
            diff = np.zeros(N)
            for h in HIST:
                ah, bh = a & (hist == h), b & (hist == h)
                if ah.sum() and bh.sum():
                    diff += ah.sum() * (np.asarray(X[ah].mean(0)).ravel() - np.asarray(X[bh].mean(0)).ravel())
        else:
            diff = np.asarray(X[a].mean(0)).ravel() - np.asarray(X[b].mean(0)).ravel()
        rate = np.asarray((X[use & tr] > 0).mean(0)).ravel()
        diff = np.where(rate >= .05, diff, 0)
        up, down = np.argsort(diff)[::-1][:TOP], np.argsort(diff)[:TOP]
        te = use & ~tr
        s = np.asarray(X[te][:, up].sum(1)).ravel() - np.asarray(X[te][:, down].sum(1)).ravel()
        aucs.append(within(y[te], s, hist[te]) if pooled else roc_auc_score(y[te], s))
        if track is not None:
            for f in up[:6]:
                track[int(f)] = track.get(int(f), 0) + 1
            for f in down[:6]:
                track[-int(f) - 1] = track.get(-int(f) - 1, 0) + 1
    return aucs


def main():
    a = np.load(os.path.join(HERE, "sae", "acts.npz"))
    token, feature, value = a["token"], a["feature"], a["value"]
    conv, section = a["conv"], a["section"]
    hist, env, gave = a["hist"], a["env"], a["gave"].astype(int)
    n = len(hist)
    keep = section[token] == 0
    t, f, v = conv[token[keep]], feature[keep], value[keep]
    tk = token[keep]
    order = np.lexsort((v, f, t))
    k = t[order].astype(np.int64) * N + f[order]
    tail = np.r_[k[1:] != k[:-1], True]
    X_msg = sparse.csr_matrix((v[order][tail], (t[order][tail], f[order][tail])), shape=(n, N))
    last = np.full(n, -1)
    np.maximum.at(last, conv[section == 0], np.where(section == 0)[0])
    m = tk == last[t]
    X_last = sparse.csr_matrix((v[m], (t[m], f[m])), shape=(n, N))
    rng = np.random.default_rng(0)
    out = []
    for view, X in [("final user message", X_msg), ("last token before the reply", X_last)]:
        for task, use, pooled in [("gave vs kept, helped only", hist == "helped", False), ("gave vs kept, within each history", np.ones(n, bool), True)]:
            track = {}
            real = evaluate(X, gave, hist, env, use, pooled, range(SPLITS), track)
            null = []
            for _ in range(SHUFFLES):
                y = gave.copy()
                for h in HIST:
                    i = np.where(hist == h)[0]
                    y[i] = rng.permutation(y[i])
                null.append(np.mean(evaluate(X, y, hist, env, use, pooled, range(4))))
            top = sorted(track.items(), key=lambda x: -x[1])[:10]
            rec = {"view": view, "task": task, "auc_mean": round(float(np.mean(real)), 3), "auc_min": round(float(np.min(real)), 3), "auc_max": round(float(np.max(real)), 3),
                   "null_mean": round(float(np.mean(null)), 3), "null_max": round(float(np.max(null)), 3),
                   "p": (1 + sum(x >= np.mean(real) for x in null)) / (1 + len(null)),
                   "stable_features": [{"feature": x if x >= 0 else -x - 1, "direction": "gave" if x >= 0 else "kept", "splits": c} for x, c in top]}
            out.append(rec)
            print(json.dumps(rec), flush=True)
    json.dump(out, open(os.path.join(HERE, "sae_before_reasoning.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
