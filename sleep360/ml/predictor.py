"""Inference + local explanations.

Explanations are model-agnostic "what-if" contributions: for each feature we
replace the user's value with the training-set median (the *reference*) and measure
how much the predicted probability changes. Positive = this feature pushes risk up
relative to a typical night. These are approximate and not strictly additive, which
the UI states.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

import joblib
import numpy as np

from .features import FEATURE_LABELS, FEATURE_UNITS, FEATURES, to_row

log = logging.getLogger(__name__)

LEVELS = ((0.35, "low"), (0.60, "moderate"), (1.01, "high"))


def level_for(p: float) -> str:
    for cut, name in LEVELS:
        if p < cut:
            return name
    return "high"


class FatiguePredictor:
    def __init__(self, bundle: dict):
        self.model = bundle["model"]
        self.features: list[str] = bundle["features"]
        self.card: dict = bundle["card"]
        self.reference = self.card["reference_values"]
        if self.features != FEATURES:
            raise ValueError("Model feature list does not match current feature code; retrain the model.")

    @property
    def version(self) -> str:
        return self.card["version"]

    def predict(self, features: dict) -> dict:
        x = np.asarray([to_row(features)])
        p = float(self.model.predict_proba(x)[0, 1])

        # what-if contributions
        variants = np.repeat(x, len(self.features), axis=0)
        for i, f in enumerate(self.features):
            variants[i, i] = self.reference[f]
        p_ref = self.model.predict_proba(variants)[:, 1]
        contribs = []
        for i, f in enumerate(self.features):
            delta = p - float(p_ref[i])
            contribs.append(
                {
                    "feature": f,
                    "label": FEATURE_LABELS[f],
                    "value": round(float(features[f]), 2),
                    "reference": self.reference[f],
                    "unit": FEATURE_UNITS[f],
                    "impact": round(delta, 4),
                }
            )
        contribs.sort(key=lambda c: -abs(c["impact"]))
        return {
            "probability": round(p, 4),
            "level": level_for(p),
            "model_version": self.version,
            "data_source": self.card["data_source"],
            "contributions": contribs,
            "low_confidence": features.get("_window_nights", 7) < 3,
        }


_lock = threading.Lock()
_cache: dict[str, FatiguePredictor | None] = {}


def get_predictor(path: Path) -> FatiguePredictor | None:
    """Load once per process; returns None (feature degrades gracefully) if unavailable."""
    key = str(path)
    if key in _cache:
        return _cache[key]
    with _lock:
        if key not in _cache:
            try:
                _cache[key] = FatiguePredictor(joblib.load(path))
            except Exception as exc:  # missing file, version mismatch, etc.
                log.warning("Fatigue model unavailable (%s): %s", path, exc)
                _cache[key] = None
    return _cache[key]


def reset_cache() -> None:
    _cache.clear()
