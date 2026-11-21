"""User-scoped query helpers.

All reads of user-owned data go through these helpers so ownership filtering lives
in one place. Accessing another user's object raises ``NotFound`` (404, not 403) so
the API does not even reveal that the object exists.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from werkzeug.exceptions import NotFound

from ..extensions import db
from ..models import AttendanceRecord, Semester, SleepLog, StudySession, Subject, Task, User


def user_today(user: User) -> date:
    return datetime.now(ZoneInfo(user.timezone)).date()


def user_now(user: User) -> datetime:
    return datetime.now(ZoneInfo(user.timezone)).replace(tzinfo=None, second=0, microsecond=0)


def sleep_logs(user: User, since: date | None = None, until: date | None = None) -> list[SleepLog]:
    q = select(SleepLog).where(SleepLog.user_id == user.id)
    if since:
        q = q.where(SleepLog.date >= since)
    if until:
        q = q.where(SleepLog.date <= until)
    return list(db.session.scalars(q.order_by(SleepLog.date)))


def recent_logs(user: User, days: int, end: date | None = None) -> list[SleepLog]:
    end = end or user_today(user)
    return sleep_logs(user, end - timedelta(days=days - 1), end)


def active_semester(user: User) -> Semester | None:
    return db.session.scalar(
        select(Semester).where(Semester.user_id == user.id, Semester.is_active.is_(True)).order_by(Semester.start_date.desc())
    )


def subjects_for(user: User, semester: Semester | None) -> list[Subject]:
    if semester is None:
        return []
    return list(
        db.session.scalars(
            select(Subject).where(Subject.user_id == user.id, Subject.semester_id == semester.id).order_by(Subject.name)
        )
    )


def attendance_records(user: User, semester: Semester | None) -> list[AttendanceRecord]:
    if semester is None:
        return []
    return list(
        db.session.scalars(
            select(AttendanceRecord)
            .join(Subject)
            .where(Subject.user_id == user.id, Subject.semester_id == semester.id)
            .order_by(AttendanceRecord.date)
        )
    )


def open_tasks(user: User) -> list[Task]:
    return list(
        db.session.scalars(
            select(Task)
            .where(Task.user_id == user.id, Task.done.is_(False))
            .order_by(Task.due_at.is_(None), Task.due_at, Task.priority)
        )
    )


def study_sessions(user: User, since: datetime) -> list[StudySession]:
    return list(
        db.session.scalars(
            select(StudySession)
            .where(StudySession.user_id == user.id, StudySession.started_at >= since)
            .order_by(StudySession.started_at)
        )
    )


def get_owned(model, obj_id: int, user: User):
    """Fetch a row by id that must belong to ``user`` (directly or via Subject)."""
    obj = db.session.get(model, obj_id)
    if obj is None:
        raise NotFound()
    owner = getattr(obj, "user_id", None)
    if owner is None and hasattr(obj, "subject"):
        owner = obj.subject.user_id
    if owner != user.id:
        raise NotFound()
    return obj
