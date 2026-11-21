from __future__ import annotations

from flask import request
from flask_login import current_user, login_required
from sqlalchemy import select

from ..extensions import db
from ..models import AttendanceRecord, AttendanceStatus, Semester, Subject
from ..schemas import AttendanceMarkIn, SemesterIn, SubjectIn, SubjectUpdateIn
from ..services import queries
from ..services.attendance import monthly_history, overall, summarize_subject, weekly_trend
from . import APIError, bp, parse


# ── semesters ────────────────────────────────────────────────────────────
@bp.get("/semesters")
@login_required
def list_semesters():
    sems = db.session.scalars(select(Semester).where(Semester.user_id == current_user.id).order_by(Semester.start_date.desc()))
    today = queries.user_today(current_user)
    out = []
    for s in sems:
        subs = [summarize_subject(x, current_user.attendance_target, today) for x in s.subjects]
        out.append({**s.to_dict(), "overall": overall(subs), "subject_count": len(subs)})
    return {"items": out}


@bp.post("/semesters")
@login_required
def create_semester():
    data = parse(SemesterIn)
    if data.is_active:  # only one active semester at a time
        for s in db.session.scalars(select(Semester).where(Semester.user_id == current_user.id, Semester.is_active.is_(True))):
            s.is_active = False
    sem = Semester(user_id=current_user.id, **data.model_dump())
    db.session.add(sem)
    db.session.commit()
    return sem.to_dict(), 201


@bp.post("/semesters/<int:sem_id>/activate")
@login_required
def activate_semester(sem_id: int):
    sem = queries.get_owned(Semester, sem_id, current_user)
    for s in db.session.scalars(select(Semester).where(Semester.user_id == current_user.id)):
        s.is_active = s.id == sem.id
    db.session.commit()
    return sem.to_dict()


@bp.delete("/semesters/<int:sem_id>")
@login_required
def delete_semester(sem_id: int):
    db.session.delete(queries.get_owned(Semester, sem_id, current_user))
    db.session.commit()
    return "", 204


# ── subjects ─────────────────────────────────────────────────────────────
@bp.get("/attendance")
@login_required
def attendance_overview():
    sem_id = request.args.get("semester_id", type=int)
    sem = queries.get_owned(Semester, sem_id, current_user) if sem_id else queries.active_semester(current_user)
    today = queries.user_today(current_user)
    subs = queries.subjects_for(current_user, sem)
    summaries = [summarize_subject(s, current_user.attendance_target, today) for s in subs]
    records = queries.attendance_records(current_user, sem)
    return {
        "semester": sem.to_dict() if sem else None,
        "default_target": current_user.attendance_target,
        "overall": overall(summaries),
        "subjects": [s.to_dict() for s in summaries],
        "weekly": weekly_trend(records, 10, today),
        "monthly": monthly_history(records),
        "today": today.isoformat(),
        "marked_today": [r.to_dict() for r in records if r.date == today],
    }


@bp.post("/subjects")
@login_required
def create_subject():
    data = parse(SubjectIn)
    queries.get_owned(Semester, data.semester_id, current_user)
    s = Subject(user_id=current_user.id, **data.model_dump())
    db.session.add(s)
    db.session.commit()
    return summarize_subject(s, current_user.attendance_target, queries.user_today(current_user)).to_dict(), 201


@bp.patch("/subjects/<int:subject_id>")
@login_required
def update_subject(subject_id: int):
    s = queries.get_owned(Subject, subject_id, current_user)
    data = parse(SubjectUpdateIn).model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(s, k, v)
    if s.initial_attended > s.initial_conducted:
        raise APIError(422, "validation_error", "Attended classes cannot exceed conducted classes")
    db.session.commit()
    return summarize_subject(s, current_user.attendance_target, queries.user_today(current_user)).to_dict()


@bp.delete("/subjects/<int:subject_id>")
@login_required
def delete_subject(subject_id: int):
    db.session.delete(queries.get_owned(Subject, subject_id, current_user))
    db.session.commit()
    return "", 204


@bp.get("/subjects/<int:subject_id>/records")
@login_required
def subject_records(subject_id: int):
    s = queries.get_owned(Subject, subject_id, current_user)
    recs = sorted(s.records, key=lambda r: (r.date, r.period), reverse=True)
    return {"items": [r.to_dict() for r in recs[:200]]}


# ── marking ──────────────────────────────────────────────────────────────
@bp.post("/attendance")
@login_required
def mark_attendance():
    data = parse(AttendanceMarkIn)
    s = queries.get_owned(Subject, data.subject_id, current_user)
    today = queries.user_today(current_user)
    if data.date > today:
        raise APIError(422, "validation_error", "Can't mark attendance for a future date")
    rec = db.session.scalar(
        select(AttendanceRecord).where(
            AttendanceRecord.subject_id == s.id, AttendanceRecord.date == data.date, AttendanceRecord.period == data.period
        )
    )
    created = rec is None
    if created:
        rec = AttendanceRecord(subject_id=s.id, date=data.date, period=data.period, status=AttendanceStatus(data.status))
        db.session.add(rec)
    else:
        rec.status = AttendanceStatus(data.status)
    db.session.commit()
    return {"record": rec.to_dict(), "subject": summarize_subject(s, current_user.attendance_target, today).to_dict()}, (
        201 if created else 200
    )


@bp.delete("/attendance/<int:record_id>")
@login_required
def delete_attendance(record_id: int):
    rec = queries.get_owned(AttendanceRecord, record_id, current_user)
    db.session.delete(rec)
    db.session.commit()
    return "", 204


@bp.get("/attendance/simulate")
@login_required
def simulate():
    """What-if: attend/miss the next N classes of a subject."""
    s = queries.get_owned(Subject, request.args.get("subject_id", type=int) or 0, current_user)
    attend = max(0, min(500, request.args.get("attend", 0, type=int)))
    miss = max(0, min(500, request.args.get("miss", 0, type=int)))
    sm = summarize_subject(s, current_user.attendance_target, queries.user_today(current_user))
    a, c = sm.attended + attend, sm.conducted + attend + miss
    return {
        "subject_id": s.id,
        "attended": a,
        "conducted": c,
        "percentage": round(a / c * 100, 2) if c else None,
        "target": sm.target,
        "meets_target": bool(c) and a / c * 100 >= sm.target,
    }
