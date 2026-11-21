from __future__ import annotations

from datetime import date, datetime, time, timedelta

from flask import request
from flask_login import current_user, login_required
from sqlalchemy import select

from ..extensions import db
from ..models import StudySession, Subject, Task, TaskKind, utcnow
from ..schemas import StudySessionIn, TaskIn, TaskUpdateIn
from ..services import queries
from ..services.planner import build_plan, productivity, remaining_minutes
from ..services.sleep_metrics import duration_hours
from . import APIError, bp, parse


def _check_refs(subject_id: int | None, task_id: int | None = None):
    if subject_id is not None:
        queries.get_owned(Subject, subject_id, current_user)
    if task_id is not None:
        queries.get_owned(Task, task_id, current_user)


def _task_out(t: Task, sessions: list[StudySession]) -> dict:
    return {**t.to_dict(), "remaining_minutes": remaining_minutes(t, sessions)}


@bp.get("/tasks")
@login_required
def list_tasks():
    status = request.args.get("status", "open")
    q = select(Task).where(Task.user_id == current_user.id)
    if status == "open":
        q = q.where(Task.done.is_(False))
    elif status == "done":
        q = q.where(Task.done.is_(True))
    q = q.order_by(Task.done, Task.due_at.is_(None), Task.due_at, Task.priority).limit(200)
    sessions = list(
        db.session.scalars(select(StudySession).where(StudySession.user_id == current_user.id, StudySession.task_id.is_not(None)))
    )
    return {"items": [_task_out(t, sessions) for t in db.session.scalars(q)]}


@bp.post("/tasks")
@login_required
def create_task():
    data = parse(TaskIn)
    _check_refs(data.subject_id)
    fields = data.model_dump()
    fields["kind"] = TaskKind(fields["kind"])
    if fields["due_at"]:
        fields["due_at"] = fields["due_at"].replace(tzinfo=None)
    t = Task(user_id=current_user.id, **fields)
    db.session.add(t)
    db.session.commit()
    return _task_out(t, []), 201


@bp.patch("/tasks/<int:task_id>")
@login_required
def update_task(task_id: int):
    t = queries.get_owned(Task, task_id, current_user)
    data = parse(TaskUpdateIn).model_dump(exclude_unset=True)
    if "subject_id" in data:
        _check_refs(data["subject_id"])
    if "kind" in data and data["kind"]:
        data["kind"] = TaskKind(data["kind"])
    if data.get("due_at"):
        data["due_at"] = data["due_at"].replace(tzinfo=None)
    if "done" in data:
        t.completed_at = utcnow() if data["done"] else None
    for k, v in data.items():
        setattr(t, k, v)
    db.session.commit()
    return _task_out(t, list(t.user.study_sessions))


@bp.delete("/tasks/<int:task_id>")
@login_required
def delete_task(task_id: int):
    db.session.delete(queries.get_owned(Task, task_id, current_user))
    db.session.commit()
    return "", 204


@bp.get("/study-sessions")
@login_required
def list_sessions():
    days = max(1, min(90, request.args.get("days", 14, type=int)))
    since = datetime.combine(queries.user_today(current_user) - timedelta(days=days - 1), time())
    return {"items": [s.to_dict() for s in reversed(queries.study_sessions(current_user, since))]}


@bp.post("/study-sessions")
@login_required
def create_session():
    data = parse(StudySessionIn)
    _check_refs(data.subject_id, data.task_id)
    fields = data.model_dump()
    fields["started_at"] = fields["started_at"].replace(tzinfo=None)
    if fields["started_at"] > queries.user_now(current_user) + timedelta(minutes=5):
        raise APIError(422, "validation_error", "Study session can't start in the future")
    if fields["task_id"] and not fields["subject_id"]:
        fields["subject_id"] = db.session.get(Task, fields["task_id"]).subject_id
    s = StudySession(user_id=current_user.id, **fields)
    db.session.add(s)
    db.session.commit()
    return s.to_dict(), 201


@bp.delete("/study-sessions/<int:session_id>")
@login_required
def delete_session(session_id: int):
    db.session.delete(queries.get_owned(StudySession, session_id, current_user))
    db.session.commit()
    return "", 204


@bp.get("/planner")
@login_required
def plan():
    now = queries.user_now(current_user)
    day = now.date()
    if request.args.get("date"):
        try:
            day = date.fromisoformat(request.args["date"])
        except ValueError:
            raise APIError(400, "bad_request", "'date' must be YYYY-MM-DD")
    start = None
    if request.args.get("start"):
        try:
            start = time.fromisoformat(request.args["start"])
        except ValueError:
            raise APIError(400, "bad_request", "'start' must be HH:MM")
    max_minutes = max(30, min(600, request.args.get("max_minutes", 240, type=int)))
    tasks = queries.open_tasks(current_user)
    sessions = list(
        db.session.scalars(select(StudySession).where(StudySession.user_id == current_user.id, StudySession.task_id.is_not(None)))
    )
    last = next((x for x in queries.recent_logs(current_user, 1, day)), None)
    return build_plan(
        current_user,
        day,
        now,
        tasks,
        sessions,
        duration_hours(last) if last else None,
        start=start,
        max_daily_minutes=max_minutes,
    )


@bp.get("/productivity")
@login_required
def get_productivity():
    today = queries.user_today(current_user)
    days = max(7, min(60, request.args.get("days", 14, type=int)))
    since = datetime.combine(today - timedelta(days=days - 1), time())
    return productivity(
        current_user, queries.study_sessions(current_user, since), queries.recent_logs(current_user, days, today), today, days
    )
