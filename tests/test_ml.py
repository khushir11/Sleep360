from datetime import date

import numpy as np
import pytest

from sleep360.ml.features import FEATURES, build_features
from sleep360.ml.predictor import FatiguePredictor, level_for
from sleep360.ml.synthetic import SimConfig, simulate
from sleep360.ml.train import select, train

from .test_sleep import L


def test_features_shared_definition():
    logs = [L(date(2026, 11, i), "23:00", "07:00") for i in range(1, 8)] + [L(date(2026, 11, 8), "01:00", "07:00", q=4)]
    f = build_features(logs, date(2026, 11, 8), 8.0)
    assert f["sleep_hours"] == 6.0
    assert f["sleep_debt_7d"] == pytest.approx(2.0)
    assert f["bedtime_sd_7d"] > 0
    assert f["stress"] == 5.0  # documented imputation
    assert build_features(logs, date(2026, 12, 1), 8.0) is None


def test_simulation_is_deterministic_and_grouped():
    X1, y1, g1 = simulate(SimConfig(n_students=20, days=20, seed=1))
    X2, y2, g2 = simulate(SimConfig(n_students=20, days=20, seed=1))
    assert np.array_equal(X1, X2) and np.array_equal(y1, y2)
    assert X1.shape[1] == len(FEATURES) and len(set(g1)) == 20
    assert 0.1 < y1.mean() < 0.7


def test_selection_prefers_simpler_model_when_close():
    s = {
        "logistic_regression": {"roc_auc": {"mean": 0.740}},
        "random_forest": {"roc_auc": {"mean": 0.744}},
        "gradient_boosting": {"roc_auc": {"mean": 0.739}},
    }
    assert select(s) == "logistic_regression"
    s["gradient_boosting"]["roc_auc"]["mean"] = 0.80
    assert select(s) == "gradient_boosting"


def test_train_beats_baselines_and_writes_card(tmp_path):
    card = train(out_path=tmp_path / "m.joblib", sim=SimConfig(n_students=60, days=40, seed=3))
    cmp_ = card["comparison"]
    best = cmp_[card["selected_model"]]["roc_auc"]["mean"]
    assert best > cmp_["baseline_rule_sleep_lt_6h"]["roc_auc"]["mean"] > 0.5 - 1e-9
    assert card["data_source"] == "synthetic" and "SIMULATED" in card["data_disclaimer"]
    assert (tmp_path / "model_card.json").exists()


def test_predictor_monotonic_in_sleep_and_explains(app):
    import joblib

    p = FatiguePredictor(joblib.load(app.config["MODEL_PATH"]))
    base = {
        "sleep_hours": 8,
        "sleep_hours_7d": 8,
        "sleep_debt_7d": 0,
        "bedtime_sd_7d": 15,
        "bedtime_rel_hours": 4.75,
        "quality": 8,
        "stress": 3,
        "screen_minutes": 15,
        "caffeine_late": 0,
        "exercise_minutes": 30,
    }
    bad = {**base, "sleep_hours": 4.5, "sleep_hours_7d": 5.5, "sleep_debt_7d": 15, "stress": 9, "quality": 3}
    good_p, bad_p = p.predict(base), p.predict(bad)
    assert bad_p["probability"] > good_p["probability"]
    assert bad_p["level"] in ("moderate", "high") and good_p["level"] == "low"
    top = bad_p["contributions"][0]
    assert top["impact"] > 0 and top["feature"] in FEATURES


def test_levels():
    assert level_for(0.1) == "low" and level_for(0.5) == "moderate" and level_for(0.9) == "high"


def test_model_card_endpoint_is_public(client):
    r = client.get("/api/v1/model")
    assert r.status_code == 200 and r.json["data_source"] == "synthetic"
