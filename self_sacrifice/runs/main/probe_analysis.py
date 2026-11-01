"""Linear probes on activations from before any reasoning: can they tell conversations that went on to give from those that kept?

Split: 70% of environments for training and 30% held out, split by environment so no prompt text crosses over. The layer and position are chosen
by cross-validation inside the training environments, and only that choice is scored on the held-out environments. Each probe is PCA to 50
dimensions, then logistic regression, both fitted on training data only. Tasks:
  gave_within_history  gave vs kept, with history means removed, scored within each history and averaged (weighted by gives)
  gave_helped          gave vs kept among helped conversations only
  history_helped_none  helped vs none, as a positive control that the method can read the prompt
Significance: shuffle decisions within history on the held-out set."""
import json, os, re
import numpy as np
from sklearn.decomposition import PCA
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold

HERE = os.path.dirname(os.path.abspath(__file__))
MOVE = re.compile(r"\$\s*give\s+\w+\s+\d+", re.I)
POSITIONS = ["last prompt token", "final user message"]
HISTORY = ["helped", "bystander", "rescued", "none"]
SEED = 0
N_SHUFFLES = 5000


def load(version):
    path = os.path.join(HERE, version.replace("-", "_") + ".jsonl")
    rows = {r["id"]: r for r in map(json.loads, open(path))}
    a = np.load(os.path.join(HERE, "activations", version + ".npz"))
    ids = [str(i) for i in a["ids"]]
    keep = [i for i, x in enumerate(ids) if not MOVE.search(rows[x]["messages"][2]["content"].replace("<agent>", ""))]
    meta = [rows[ids[i]] for i in keep]
    return a["x"][keep], meta, a["layers"]


def fit_score(xtr, ytr, xte, seed=SEED):
    mean = xtr.mean(0)
    pca = PCA(50, random_state=seed, svd_solver="randomized").fit(xtr - mean)
    ztr, zte = pca.transform(xtr - mean), pca.transform(xte - mean)
    scale = ztr.std(0) + 1e-6
    clf = LogisticRegression(C=0.1, class_weight="balanced", max_iter=1000).fit(ztr / scale, ytr)
    return clf.decision_function(zte / scale)


def center(x, hist, reference=None):
    """remove each history's mean, using training means for test data"""
    means = reference or {h: x[hist == h].mean(0) for h in HISTORY if (hist == h).any()}
    out = x.copy()
    for h, m in means.items():
        out[hist == h] -= m
    return out, means


def within_auc(y, s, hist):
    total = weight = 0
    for h in HISTORY:
        m = hist == h
        if y[m].sum() and (1 - y[m]).sum():
            total += roc_auc_score(y[m], s[m]) * y[m].sum()
            weight += y[m].sum()
    return total / weight if weight else float("nan")


def task_data(task, meta):
    hist = np.array([r["hist"] for r in meta])
    gave = np.array([int(r["gives_to_X"]) for r in meta])
    if task == "gave_within_history":
        return np.ones(len(meta), bool), gave
    if task == "gave_helped":
        return hist == "helped", gave
    return np.isin(hist, ["helped", "none"]), (hist == "helped").astype(int)


def run_task(task, x, meta, layers, train_envs):
    use, y = task_data(task, meta)
    hist = np.array([r["hist"] for r in meta])
    envs = np.array([r["env"] for r in meta])
    train = use & np.isin(envs, train_envs)
    test = use & ~np.isin(envs, train_envs)
    within = task == "gave_within_history"
    grid = []
    for li, layer in enumerate(layers):
        for p, position in enumerate(POSITIONS):
            xs = x[:, li, p]
            scores = np.full(len(meta), np.nan)
            folds = StratifiedGroupKFold(5, shuffle=True, random_state=SEED)
            idx = np.where(train)[0]
            for a, b in folds.split(xs[idx], y[idx], envs[idx]):
                tr, te = idx[a], idx[b]
                xa, xb = xs[tr], xs[te]
                if within:
                    xa, means = center(xa, hist[tr])
                    xb, _ = center(xb, hist[te], means)
                scores[te] = fit_score(xa, y[tr], xb)
            cv = within_auc(y[idx], scores[idx], hist[idx]) if within else roc_auc_score(y[idx], scores[idx])
            grid.append({"layer": int(layer), "position": position, "cv_auc": round(float(cv), 3)})
    best = max(grid, key=lambda g: g["cv_auc"])
    li, p = list(layers).index(best["layer"]), POSITIONS.index(best["position"])
    xs = x[:, li, p]
    xa, xb = xs[train], xs[test]
    if within:
        xa, means = center(xa, hist[train])
        xb, _ = center(xb, hist[test], means)
    s = fit_score(xa, y[train], xb)
    yt, ht = y[test], hist[test]
    score = (lambda yy: within_auc(yy, s, ht)) if within else (lambda yy: roc_auc_score(yy, s))
    real = float(score(yt))
    rng = np.random.default_rng(SEED)
    hits = 0
    for _ in range(N_SHUFFLES):
        yy = yt.copy()
        for h in HISTORY:
            m = np.where(ht == h)[0]
            if task != "history_helped_none":
                yy[m] = rng.permutation(yy[m])
        if task == "history_helped_none":
            yy = rng.permutation(yy)
        hits += score(yy) >= real
    return {"task": task, "chosen_layer": best["layer"], "chosen_position": best["position"], "cv_auc": best["cv_auc"], "test_auc": round(real, 3),
            "test_p": (hits + 1) / (N_SHUFFLES + 1), "train_n": int(train.sum()), "train_positive": int(y[train].sum()), "test_n": int(test.sum()),
            "test_positive": int(y[test].sum()), "grid": grid}


def main():
    out = []
    for version in ["main-fixed-first-response", "main"]:
        x, meta, layers = load(version)
        envs = sorted({r["env"] for r in meta})
        rng = np.random.default_rng(SEED)
        train_envs = list(rng.choice(envs, int(len(envs) * 0.7), replace=False))
        for task in ["history_helped_none", "gave_within_history", "gave_helped"]:
            r = run_task(task, x, meta, layers, train_envs)
            r["version"] = version
            out.append(r)
            print({k: v for k, v in r.items() if k != "grid"}, flush=True)
    json.dump(out, open(os.path.join(HERE, "probe_summary.json"), "w"), indent=2)


if __name__ == "__main__":
    main()
