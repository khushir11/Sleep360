"""Model training, evaluation and selection.

Run with ``flask ml train`` (synthetic) or ``flask ml train --source db``.

Evaluation protocol
-------------------
* 5-fold **GroupKFold** by student: every day of a given student is either in the
  training folds or the test fold, never both. Random row-level splits would leak
  each student's persistent traits and inflate scores.
* Metrics: ROC-AUC (ranking), average precision (PR-AUC; robust to imbalance),
  Brier score (probability calibration), F1 and accuracy at a 0.5 threshold.
* Baselines: always predicting the base rate, and a one-rule heuristic
  ("fatigued if slept < 6h") so model gains are measured against something simple.
* Selection: highest mean ROC-AUC; if a simpler model is within 0.005 it wins
  (interpretability is worth more than a rounding-error gain).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import joblib
import numpy as np
import sklearn
from sklearn.base import clone
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, average_precision_score, brier_score_loss, f1_score, roc_auc_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .features import FEATURE_LABELS, FEATURES
from .synthetic import GENERATIVE_COEFFICIENTS, SimConfig, simulate

COMPLEXITY_ORDER = ["logistic_regression", "random_forest", "gradient_boosting"]


def candidate_models(seed: int = 42) -> dict:
    return {
        "logistic_regression": make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, C=1.0)),
        "random_forest": RandomForestClassifier(n_estimators=200, max_depth=8, min_samples_leaf=20, n_jobs=-1, random_state=seed),
        "gradient_boosting": HistGradientBoostingClassifier(
            max_iter=250, learning_rate=0.05, max_depth=4, l2_regularization=1.0, random_state=seed
        ),
    }


def _metrics(y_true, p) -> dict:
    return {
        "roc_auc": float(roc_auc_score(y_true, p)),
        "avg_precision": float(average_precision_score(y_true, p)),
        "brier": float(brier_score_loss(y_true, p)),
        "f1": float(f1_score(y_true, (p >= 0.5).astype(int), zero_division=0)),
        "accuracy": float(accuracy_score(y_true, (p >= 0.5).astype(int))),
    }


def _summarize(fold_metrics: list[dict]) -> dict:
    keys = fold_metrics[0].keys()
    return {
        k: {
            "mean": round(float(np.mean([m[k] for m in fold_metrics])), 4),
            "std": round(float(np.std([m[k] for m in fold_metrics])), 4),
        }
        for k in keys
    }


def evaluate(X, y, groups, n_splits: int = 5, seed: int = 42) -> dict:
    cv = GroupKFold(n_splits=n_splits)
    results: dict[str, list[dict]] = {name: [] for name in candidate_models(seed)}
    results["baseline_base_rate"] = []
    results["baseline_rule_sleep_lt_6h"] = []
    sleep_idx = FEATURES.index("sleep_hours")
    for tr, te in cv.split(X, y, groups):
        for name, model in candidate_models(seed).items():
            m = clone(model).fit(X[tr], y[tr])
            results[name].append(_metrics(y[te], m.predict_proba(X[te])[:, 1]))
        base = np.full(len(te), y[tr].mean())
        results["baseline_base_rate"].append(_metrics(y[te], base))
        rule = (X[te, sleep_idx] < 6).astype(float) * 0.7 + 0.15
        results["baseline_rule_sleep_lt_6h"].append(_metrics(y[te], rule))
    return {k: _summarize(v) for k, v in results.items()}


def select(summary: dict) -> str:
    scores = {k: summary[k]["roc_auc"]["mean"] for k in COMPLEXITY_ORDER}
    best = max(scores.values())
    for name in COMPLEXITY_ORDER:  # simplest first
        if scores[name] >= best - 0.005:
            return name
    return max(scores, key=scores.get)


def load_db_dataset(min_rows: int = 200):
    """Real labelled logs from the app DB (non-demo users who supplied daytime sleepiness)."""
    from ..extensions import db
    from ..models import User
    from .features import build_features

    X, y, groups = [], [], []
    users = db.session.scalars(db.select(User).where(User.is_demo.is_(False))).all()
    for u in users:
        logs = sorted(u.sleep_logs, key=lambda x: x.date)
        for log in logs:
            if log.daytime_sleepiness is None:
                continue
            f = build_features(logs, log.date, u.sleep_goal_hours)
            if f["_window_nights"] < 3:
                continue
            X.append([f[k] for k in FEATURES])
            y.append(int(log.daytime_sleepiness >= 7))
            groups.append(u.id)
    if len(X) < min_rows or len(set(groups)) < 10 or len(set(y)) < 2:
        raise ValueError(
            f"Not enough real labelled data: {len(X)} rows from {len(set(groups))} users "
            f"(need >= {min_rows} rows, >= 10 users, both classes)."
        )
    return np.asarray(X, float), np.asarray(y, int), np.asarray(groups)


def train(source: str = "synthetic", out_path: Path | None = None, seed: int = 42, sim: SimConfig | None = None) -> dict:
    if source == "synthetic":
        sim = sim or SimConfig(seed=seed)
        X, y, groups = simulate(sim)
    elif source == "db":
        X, y, groups = load_db_dataset()
    else:
        raise ValueError("source must be 'synthetic' or 'db'")

    summary = evaluate(X, y, groups, seed=seed)
    chosen = select(summary)

    # Global importance on a held-out group split (permutation importance, ROC-AUC drop)
    tr, te = next(GroupKFold(n_splits=5).split(X, y, groups))
    probe = clone(candidate_models(seed)[chosen]).fit(X[tr], y[tr])
    pi = permutation_importance(probe, X[te], y[te], scoring="roc_auc", n_repeats=5, random_state=seed)
    importance = sorted(
        (
            {"feature": f, "label": FEATURE_LABELS[f], "importance": round(float(m), 4)}
            for f, m in zip(FEATURES, pi.importances_mean, strict=True)
        ),
        key=lambda d: -d["importance"],
    )

    final = clone(candidate_models(seed)[chosen])
    if chosen != "logistic_regression":
        final = CalibratedClassifierCV(final, method="isotonic", cv=3)  # trees are often over/under-confident
    final.fit(X, y)

    version = f"{chosen}-{source}-{datetime.now(UTC).strftime('%Y%m%d%H%M')}"
    card = {
        "version": version,
        "trained_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "data_source": source,
        "data_disclaimer": (
            "Trained on SIMULATED data generated from assumed relationships. Metrics show how well the "
            "pipeline recovers a known synthetic signal; they are not evidence about real students."
            if source == "synthetic"
            else "Trained on self-reported logs from consenting non-demo users of this deployment."
        ),
        "target": "Next-day fatigue: self-reported daytime sleepiness >= 7 on a 1-10 scale",
        "features": [{"name": f, "label": FEATURE_LABELS[f]} for f in FEATURES],
        "n_rows": int(len(y)),
        "n_groups": int(len(set(groups.tolist()))),
        "positive_rate": round(float(y.mean()), 4),
        "cv": "5-fold GroupKFold by student",
        "selected_model": chosen,
        "selection_rule": "highest mean ROC-AUC; simpler model preferred if within 0.005",
        "comparison": summary,
        "permutation_importance": importance,
        "reference_values": {f: round(float(np.median(X[:, i])), 3) for i, f in enumerate(FEATURES)},
        "generative_coefficients": GENERATIVE_COEFFICIENTS if source == "synthetic" else None,
        "sklearn_version": sklearn.__version__,
        "limitations": [
            "Not a medical device; does not diagnose sleep disorders or fatigue conditions.",
            "Self-reported inputs are noisy and subject to recall bias.",
            "Synthetic training data encodes the authors' assumptions, not measured effects.",
            "Probabilities are calibrated on the training distribution only.",
        ],
    }
    out_path = Path(out_path) if out_path else Path(__file__).parent / "artifacts" / "fatigue_model.joblib"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": final, "features": FEATURES, "card": card}, out_path, compress=3)
    out_path.with_name("model_card.json").write_text(json.dumps(card, indent=2))
    return card
