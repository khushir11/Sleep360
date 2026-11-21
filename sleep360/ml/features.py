"""Feature engineering shared by training and inference.

The *same* function turns a user's log history into a feature vector both when the
synthetic training set is built and when the live app scores a real user. Sharing
this code path prevents training/serving skew.

Missing optional inputs are imputed with fixed, documented defaults (not learned
means), so a prediction for a user does not depend on other users' data.
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from datetime import date, timedelta

from ..services.sleep_metrics import duration_hours, evening_minutes

FEATURES: list[str] = [
    "sleep_hours",
    "sleep_hours_7d",
    "sleep_debt_7d",
    "bedtime_sd_7d",
    "bedtime_rel_hours",
    "quality",
    "stress",
    "screen_minutes",
    "caffeine_late",
    "exercise_minutes",
]

FEATURE_LABELS: dict[str, str] = {
    "sleep_hours": "Last night's sleep",
    "sleep_hours_7d": "7-day average sleep",
    "sleep_debt_7d": "7-day sleep debt",
    "bedtime_sd_7d": "Bedtime irregularity",
    "bedtime_rel_hours": "Bedtime (lateness)",
    "quality": "Sleep quality",
    "stress": "Stress level",
    "screen_minutes": "Screen time before bed",
    "caffeine_late": "Caffeine after 2pm",
    "exercise_minutes": "Exercise",
}

FEATURE_UNITS: dict[str, str] = {
    "sleep_hours": "h",
    "sleep_hours_7d": "h",
    "sleep_debt_7d": "h",
    "bedtime_sd_7d": "min",
    "bedtime_rel_hours": "h after 18:00",
    "quality": "/10",
    "stress": "/10",
    "screen_minutes": "min",
    "caffeine_late": "",
    "exercise_minutes": "min",
}

IMPUTE_DEFAULTS = {"stress": 5.0, "screen_minutes": 30.0, "caffeine_late": 0.0, "exercise_minutes": 20.0}


def build_features(logs: Sequence, target: date, goal_hours: float) -> dict | None:
    """Features for the night ending on ``target`` using the preceding 7-day window.

    ``logs`` may be in any order and may include dates outside the window.
    Returns None if there is no log for ``target``.
    """
    by_date = {x.date: x for x in logs}
    today = by_date.get(target)
    if today is None:
        return None
    window = [by_date[d] for d in (target - timedelta(days=i) for i in range(7)) if d in by_date]
    durs = [duration_hours(x) for x in window]
    beds = [evening_minutes(x.bedtime) for x in window]

    def opt(attr: str, key: str, cast=float) -> float:
        v = getattr(today, attr, None)
        return float(cast(v)) if v is not None else IMPUTE_DEFAULTS[key]

    return {
        "sleep_hours": round(duration_hours(today), 3),
        "sleep_hours_7d": round(statistics.mean(durs), 3),
        "sleep_debt_7d": round(sum(max(0.0, goal_hours - d) for d in durs), 3),
        "bedtime_sd_7d": round(statistics.pstdev(beds), 2) if len(beds) >= 3 else 0.0,
        "bedtime_rel_hours": round(evening_minutes(today.bedtime) / 60, 3),
        "quality": float(today.quality),
        "stress": opt("stress", "stress"),
        "screen_minutes": opt("screen_minutes_before_bed", "screen_minutes"),
        "caffeine_late": opt("caffeine_after_2pm", "caffeine_late", cast=int),
        "exercise_minutes": opt("exercise_minutes", "exercise_minutes"),
        "_window_nights": len(window),
    }


def to_row(features: dict) -> list[float]:
    return [float(features[f]) for f in FEATURES]
