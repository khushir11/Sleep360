from __future__ import annotations

from datetime import date, timedelta

from flask import request
from flask_login import current_user, login_required
from sqlalchemy import select

from ..extensions import db
from ..models import SleepLog
from ..schemas import SleepLogIn
from ..services import assessments, queries
from ..services.importer import import_csv
from ..services.sleep_metrics import bedtime_plan
from . import APIError, bp, parse


def _date_arg(name: str) -> date | None:
    v = request.args.get(name)
    if not v:
        return None
    try:
        return date.fromisoformat(v)
    except ValueError:
        raise APIError(400, "bad_request", f"'{name}' must be YYYY-MM-DD")


@bp.get("/sleep")
@login_required
def list_sleep():
    end = _date_arg("end") or queries.user_today(current_user)
    start = _date_arg("start") or end - timedelta(days=29)
    if (end - start).days > 366:
        raise APIError(400, "bad_request", "Range cannot exceed one year")
    logs = queries.sleep_logs(current_user, start, end)
    return {"items": [x.to_dict() for x in reversed(logs)], "start": start.isoformat(), "end": end.isoformat()}


@bp.post("/sleep")
@login_required
def upsert_sleep():
    """Create or replace the log for the wake date (idempotent per night)."""
    data = parse(SleepLogIn)
    today = queries.user_today(current_user)
    if data.date > today:
        raise APIError(422, "validation_error", "You can't log a night that hasn't happened yet")
    log = db.session.scalar(select(SleepLog).where(SleepLog.user_id == current_user.id, SleepLog.date == data.date))
    created = log is None
    if created:
        log = SleepLog(user_id=current_user.id, date=data.date)
        db.session.add(log)
    for k, v in data.model_dump().items():
        setattr(log, k, v)
    db.session.commit()
    assessments.after_log_change(current_user, data.date)
    ra = assessments.assess_day(current_user, data.date)
    prev = db.session.scalar(
        select(assessments.RiskAssessment)
        .where(assessments.RiskAssessment.user_id == current_user.id, assessments.RiskAssessment.date < data.date)
        .order_by(assessments.RiskAssessment.date.desc())
    )
    return {
        "log": log.to_dict(),
        "assessment": assessments.assessment_dict(ra),
        "change": assessments.explain_change(ra, prev),
        "created": created,
    }, (201 if created else 200)


@bp.delete("/sleep/<int:log_id>")
@login_required
def delete_sleep(log_id: int):
    log = queries.get_owned(SleepLog, log_id, current_user)
    d = log.date
    db.session.delete(log)
    db.session.commit()
    assessments.after_log_change(current_user, d)
    return "", 204


@bp.post("/sleep/import")
@login_required
def import_sleep():
    f = request.files.get("file")
    if f is None or not f.filename:
        raise APIError(400, "bad_request", "Attach a CSV file in the 'file' field")
    if not f.filename.lower().endswith((".csv", ".tsv", ".txt")):
        raise APIError(400, "bad_request", "Only CSV files are supported")
    report = import_csv(current_user, f.read(), overwrite=request.form.get("overwrite") == "true")
    return {"report": report.to_dict()}


@bp.get("/sleep/bedtime-plan")
@login_required
def get_bedtime_plan():
    return bedtime_plan(current_user.target_wake_time, current_user.sleep_goal_hours)
