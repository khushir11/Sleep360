"""Daily assessment: sleep score + fatigue model, persisted per user-day.

Persisting a snapshot lets us answer "why did my score / risk change?" by diffing
two days' component scores and model contributions.
"""

from __future__ import annotations

from datetime import date, timedelta

from flask import current_app
from sqlalchemy import select

from ..extensions import db
from ..ml.features import build_features
from ..ml.predictor import get_predictor
from ..models import RiskAssessment, SleepLog, User
from . import queries
from .sleep_metrics import sleep_score


def assess_day(user: User, day: date, commit: bool = True) -> RiskAssessment | None:
    history = queries.sleep_logs(user, day - timedelta(days=14), day)
    log = next((x for x in history if x.date == day), None)
    existing = db.session.scalar(select(RiskAssessment).where(RiskAssessment.user_id == user.id, RiskAssessment.date == day))
    if log is None:
        if existing:
            db.session.delete(existing)
            if commit:
                db.session.commit()
        return None

    score = sleep_score(log, history, user.sleep_goal_hours, user.target_wake_time)
    feats = build_features(history, day, user.sleep_goal_hours)
    predictor = get_predictor(current_app.config["MODEL_PATH"])
    pred = predictor.predict(feats) if predictor else None

    ra = existing or RiskAssessment(user_id=user.id, date=day)
    ra.sleep_score = score.total
    ra.fatigue_probability = pred["probability"] if pred else None
    ra.fatigue_level = pred["level"] if pred else None
    ra.model_version = pred["model_version"] if pred else None
    ra.details = {
        "score": score.to_dict(),
        "features": {k: v for k, v in feats.items() if not k.startswith("_")},
        "window_nights": feats["_window_nights"],
        "prediction": pred,
    }
    if existing is None:
        db.session.add(ra)
    if commit:
        db.session.commit()
    return ra


def reassess_range(user: User, start: date, end: date) -> None:
    """Recompute a date range (a log affects the 7-day window of the following week)."""
    d = start
    while d <= end:
        assess_day(user, d, commit=False)
        d += timedelta(days=1)
    db.session.commit()


def after_log_change(user: User, day: date) -> None:
    today = queries.user_today(user)
    reassess_range(user, day, min(today, day + timedelta(days=7)))


def latest_two(user: User) -> list[RiskAssessment]:
    return list(
        db.session.scalars(
            select(RiskAssessment).where(RiskAssessment.user_id == user.id).order_by(RiskAssessment.date.desc()).limit(2)
        )
    )


def assessment_dict(ra: RiskAssessment | None) -> dict | None:
    if ra is None:
        return None
    return {
        "date": ra.date.isoformat(),
        "sleep_score": ra.sleep_score,
        "fatigue_probability": ra.fatigue_probability,
        "fatigue_level": ra.fatigue_level,
        "model_version": ra.model_version,
        **ra.details,
    }


COMPONENT_LABELS = {
    "duration": "sleep duration",
    "regularity": "bedtime regularity",
    "quality": "sleep quality",
    "timing": "bedtime timing",
}


def explain_change(current: RiskAssessment | None, previous: RiskAssessment | None) -> dict:
    """Plain-language explanation of what moved between two assessments."""
    if current is None:
        return {"summary": "Log a night of sleep to get your first score.", "drivers": []}
    if previous is None:
        return {"summary": "This is your first scored night. Changes will be explained from tomorrow.", "drivers": []}

    cur_c = current.details["score"]["components"]
    prev_c = previous.details["score"]["components"]
    drivers = []
    for k, label in COMPONENT_LABELS.items():
        delta = round(cur_c[k]["points"] - prev_c[k]["points"], 1)
        if abs(delta) >= 1:
            drivers.append({"component": k, "label": label, "delta": delta})
    drivers.sort(key=lambda d: -abs(d["delta"]))

    score_delta = round(current.sleep_score - previous.sleep_score, 1)
    fe_c, fe_p = current.details["features"], previous.details["features"]
    facts = []
    dh = fe_c["sleep_hours"] - fe_p["sleep_hours"]
    if abs(dh) >= 0.25:
        facts.append(f"you slept {abs(dh):.1f}h {'more' if dh > 0 else 'less'} than the night before")
    dq = fe_c["quality"] - fe_p["quality"]
    if abs(dq) >= 1:
        facts.append(f"rated quality {'up' if dq > 0 else 'down'} {abs(dq):.0f} point(s)")
    db_ = fe_c["bedtime_rel_hours"] - fe_p["bedtime_rel_hours"]
    if abs(db_) >= 0.5:
        facts.append(f"went to bed {abs(db_) * 60:.0f} min {'later' if db_ > 0 else 'earlier'}")

    if abs(score_delta) < 1:
        summary = f"Your sleep score is steady at {current.sleep_score:.0f}."
    else:
        direction = "rose" if score_delta > 0 else "dropped"
        summary = f"Your sleep score {direction} by {abs(score_delta):.0f} points to {current.sleep_score:.0f}"
        summary += (" because " + ", ".join(facts) + ".") if facts else "."

    risk = None
    if current.fatigue_probability is not None and previous.fatigue_probability is not None:
        dp = current.fatigue_probability - previous.fatigue_probability
        top = (current.details.get("prediction") or {}).get("contributions", [])[:2]
        risk = {
            "delta": round(dp, 3),
            "text": (
                f"Estimated fatigue risk {'increased' if dp > 0 else 'decreased'} by {abs(dp) * 100:.0f} points"
                f" ({previous.fatigue_level} → {current.fatigue_level})."
                if abs(dp) >= 0.03
                else f"Estimated fatigue risk is about the same ({current.fatigue_level})."
            ),
            "top_factors": [c["label"] for c in top if c["impact"] > 0],
        }
    return {"summary": summary, "score_delta": score_delta, "drivers": drivers, "risk": risk}


def logs_needing_assessment(user: User) -> list[SleepLog]:
    """Logs without an assessment (e.g. after a CSV import or a model retrain)."""
    assessed = set(db.session.scalars(select(RiskAssessment.date).where(RiskAssessment.user_id == user.id)))
    return [x for x in queries.sleep_logs(user) if x.date not in assessed]
