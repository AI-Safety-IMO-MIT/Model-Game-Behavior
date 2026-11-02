"""Checks that need no GPU.

1. SAE held-out: choose features on 70% of environments, test them on the other 30%, repeated over 20 splits.
2. Probes over 20 environment splits, at fixed sites, so the estimate does not rest on one split.
3. Does the text of the model's own first reply predict the decision? TF-IDF with logistic regression, same splits, in `main`.
Output: cpu_checks.json."""
import json, os, re
import numpy as np
from scipy import sparse
from scipy.stats import mannwhitneyu
from sklearn.decomposition import PCA
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

HERE = os.path.dirname(os.path.abspath(__file__))
HIST = ["helped", "bystander", "rescued", "none"]
N_FEATURES = 131072
SPLITS = 20
MOVE = re.compile(r"^[\s`]*\$\s*give\s+\w+\s+\d+", re.I | re.M)


def within_auc(y, s, hist):
    total = weight = 0
    for h in HIST:
        m = hist == h
        if 0 < y[m].sum() < m.sum():
            total += roc_auc_score(y[m], s[m]) * y[m].sum()
            weight += y[m].sum()
    return total / weight


def env_split(envs, seed):
    u = sorted(set(envs))
    rng = np.random.default_rng(seed)
    train = set(rng.choice(u, int(len(u) * .7), replace=False))
    return np.array([e in train for e in envs])


def sae_heldout():
    a = np.load(os.path.join(HERE, "sae", "acts.npz"))
    token, feature, value = a["token"], a["feature"], a["value"]
    conv, section, text = a["conv"], a["section"], a["text"]
    hist, env, gave = a["hist"], a["env"], a["gave"].astype(bool)
    n = len(hist)
    dollars = np.where((section == 1) & (np.char.find(text.astype(str), "$") >= 0))[0]
    last = np.full(n, len(conv))
    last[conv[dollars]] = dollars
    keep = (token < last[conv[token]]) & (section[token] == 1)
    t, f, v = conv[token[keep]], feature[keep], value[keep]
    order = np.lexsort((v, f, t))
    t, f, v = t[order], f[order], v[order]
    keys = t.astype(np.int64) * N_FEATURES + f
    tail = np.r_[keys[1:] != keys[:-1], True]
    X = sparse.csr_matrix((v[tail], (t[tail], f[tail])), shape=(n, N_FEATURES))
    out = {}
    tasks = {"helped vs other histories, reasoning": (np.ones(n, bool), hist == "helped"),
             "gave vs kept, helped only": (hist == "helped", gave)}
    for name, (use, y) in tasks.items():
        aucs, tracked = [], {}
        for seed in range(SPLITS):
            tr = env_split(env, seed)
            a_tr, b_tr = use & tr & y, use & tr & ~y
            diff = np.asarray(X[a_tr].mean(0)).ravel() - np.asarray(X[b_tr].mean(0)).ravel()
            top = np.argsort(diff)[::-1][:20]
            te = use & ~tr
            score = np.asarray(X[te][:, top].sum(1)).ravel()
            aucs.append(roc_auc_score(y[te], score))
            for g in top[:5]:
                tracked[int(g)] = tracked.get(int(g), 0) + 1
        out[name] = {"held_out_auc_mean": round(float(np.mean(aucs)), 3), "min": round(float(np.min(aucs)), 3), "max": round(float(np.max(aucs)), 3),
                     "top_in_most_splits": sorted(tracked.items(), key=lambda x: -x[1])[:6]}
        for g in [11638, 3337, 17978, 10590]:
            te = use
            s = X[te, g].toarray().ravel()
            out[name][f"feature_{g}_all_data_auc"] = round(float(roc_auc_score(y[te], s)), 3)
    return out


def load_version(version):
    path = os.path.join(HERE, version.replace("-", "_") + ".jsonl")
    rows = {r["id"]: r for r in map(json.loads, open(path))}
    a = np.load(os.path.join(HERE, "activations", version + ".npz"))
    ids = [str(i) for i in a["ids"]]
    keep = [i for i, x in enumerate(ids) if not MOVE.search(rows[x]["messages"][2]["content"].replace("<agent>", ""))]
    return a["x"][keep], [rows[ids[i]] for i in keep], list(a["layers"])


def probes():
    out = {}
    for version in ["main-fixed-first-response", "main"]:
        x, meta, layers = load_version(version)
        hist = np.array([r["hist"] for r in meta])
        env = np.array([r["env"] for r in meta])
        y = np.array([int(r["gives_to_X"]) for r in meta])
        for layer, p, label in [(42, 1, "layer 42, final message"), (60, 0, "layer 60, last token"), (48, 0, "layer 48, last token")]:
            xs = x[:, layers.index(layer), p]
            scores = []
            for seed in range(SPLITS):
                tr = env_split(env, seed)
                xa, xb = xs[tr].copy(), xs[~tr].copy()
                for h in HIST:
                    m = xa[hist[tr] == h].mean(0)
                    xa[hist[tr] == h] -= m
                    xb[hist[~tr] == h] -= m
                pca = PCA(50, random_state=seed, svd_solver="randomized").fit(xa)
                za, zb = pca.transform(xa), pca.transform(xb)
                sd = za.std(0) + 1e-6
                clf = LogisticRegression(C=.1, class_weight="balanced", max_iter=1000).fit(za / sd, y[tr])
                scores.append(within_auc(y[~tr], clf.decision_function(zb / sd), hist[~tr]))
            out[f"{version}: {label}"] = {"mean": round(float(np.mean(scores)), 3), "min": round(float(np.min(scores)), 3), "max": round(float(np.max(scores)), 3)}
    return out


def first_reply_text():
    rows = [json.loads(line) for line in open(os.path.join(HERE, "main.jsonl"))]
    rows = [r for r in rows if not MOVE.search(r["messages"][2]["content"].replace("<agent>", ""))]
    names = lambda r: r["order"]
    text = []
    for r in rows:
        t = r["messages"][2]["content"]
        for i, n in enumerate(r["order"]):
            role = {r["M"]: "SELF", r["X"]: "NEED", r["O"]: "OTHER", r["O2"]: "OTHER2"}[n]
            t = t.replace(n, role)
        text.append(t)
    text = np.array(text)
    hist = np.array([r["hist"] for r in rows])
    env = np.array([r["env"] for r in rows])
    y = np.array([int(r["gives_to_X"]) for r in rows])
    scores = []
    for seed in range(SPLITS):
        tr = env_split(env, seed)
        vec = TfidfVectorizer(ngram_range=(1, 2), min_df=3, sublinear_tf=True).fit(text[tr])
        clf = LogisticRegression(C=1, class_weight="balanced", max_iter=2000).fit(vec.transform(text[tr]), y[tr])
        scores.append(within_auc(y[~tr], clf.decision_function(vec.transform(text[~tr])), hist[~tr]))
    g = np.array([len(t.split()) for t in text])
    return {"first_reply_text_within_history_auc": {"mean": round(float(np.mean(scores)), 3), "min": round(float(np.min(scores)), 3), "max": round(float(np.max(scores)), 3)},
            "first_reply_length_median_gave": float(np.median(g[y == 1])), "first_reply_length_median_kept": float(np.median(g[y == 0])),
            "length_p": float(mannwhitneyu(g[y == 1], g[y == 0]).pvalue)}


def main():
    out = {"sae_held_out": sae_heldout()}
    print(json.dumps(out), flush=True)
    out["first_reply_text"] = first_reply_text()
    print(json.dumps(out["first_reply_text"]), flush=True)
    out["probes_20_splits"] = probes()
    print(json.dumps(out["probes_20_splits"]), flush=True)
    json.dump(out, open(os.path.join(HERE, "cpu_checks.json"), "w"), indent=2)


if __name__ == "__main__":
    main()
