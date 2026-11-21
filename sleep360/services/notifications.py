"""In-app notification generator.

``scan(user)`` is idempotent: each notification has a ``dedupe_key`` with a unique
constraint, so running it on every page load (or from a cron job via
``flask notifications scan``) never creates duplicates. The frontend polls the
unread list and can surface items as browser notifications when the user allows it.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..models import Notification, User, utcnow
from . import queries
from .attendance import summarize_subject
from .sleep_metrics import bedtime_plan


def _add(user: User, kind: str, key: str, title: str, body: str, link: str | None = None) -> bool:
    exists = db.session.scalar(select(Notification.id).where(Notification.user_id == user.id, Notification.dedupe_key == key))
    if exists:
        return False
    # truncate to column limits (titles embed user-supplied names)
    db.session.add(Notification(user_id=user.id, kind=kind, dedupe_key=key[:120], title=title[:140], body=body[:500], link=link))
    return True


def scan(user: User, now: datetime | None = None) -> int:
    now = now or queries.user_now(user)
    today = now.date()
    created = 0

    # 1. Missing sleep log (after 10:00)
    logged_today = any(x.date == today for x in queries.recent_logs(user, 1, today))
    if not logged_today and now.hour >= 10:
        created += _add(
            user,
            "log_reminder",
            f"log:{today}",
            "How did you sleep?",
            "Log last night in 20 seconds to keep your streak and update your insights.",
            "/sleep",
        )

    # 2. Tonight's wind-down (from 18:00)
    if now.hour >= 18:
        plan = bedtime_plan(user.target_wake_time, user.sleep_goal_hours)
        created += _add(
            user,
            "bedtime",
            f"bedtime:{today}",
            f"Wind-down starts at {plan['wind_down_start']}",
            f"Aim for lights out by {plan['bedtime']} to get {user.sleep_goal_hours:g}h before your "
            f"{plan['target_wake_time']} alarm.",
            "/sleep",
        )

    # 3. Attendance (once per subject per ISO week per status)
    sem = queries.active_semester(user)
    week = today.isocalendar()
    for s in queries.subjects_for(user, sem):
        sm = summarize_subject(s, user.attendance_target, today)
        if sm.status in ("shortage", "critical"):
            body = f"{sm.percentage:.1f}% vs {sm.target:.0f}% required. " + (
                f"Attend the next {sm.classes_needed} classes to recover."
                if sm.status == "shortage"
                else "The target is no longer reachable this semester. Speak to your faculty advisor."
            )
            created += _add(
                user,
                "attendance",
                f"att:{s.id}:{sm.status}:{week.year}-{week.week}",
                f"Attendance alert: {s.name}",
                body,
                "/attendance",
            )
        elif sm.status == "warning" and sm.safe_skips <= 1:
            created += _add(
                user,
                "attendance",
                f"att:{s.id}:warn:{week.year}-{week.week}",
                f"{s.name}: almost no skips left",
                f"You're at {sm.percentage:.1f}%. Missing {sm.safe_skips + 1} more class(es) drops you below {sm.target:.0f}%.",
                "/attendance",
            )

    # 4. Tasks due within 24h
    for t in queries.open_tasks(user):
        if t.due_at and now <= t.due_at <= now + timedelta(hours=24):
            created += _add(
                user,
                "deadline",
                f"due:{t.id}:{t.due_at:%Y%m%d%H%M}",
                f"Due soon: {t.title}",
                f"Due {t.due_at:%a %H:%M}. Check today's plan for a time slot.",
                "/planner",
            )

    # 5. Weekly report (Mondays)
    if today.weekday() == 0:
        created += _add(
            user,
            "report",
            f"report:{week.year}-{week.week}",
            "Your weekly wellness report is ready",
            "See how last week went and download it as a PDF.",
            "/insights",
        )

    try:
        db.session.commit()
    except IntegrityError:  # concurrent scan raced us on a dedupe key
        db.session.rollback()
    return created


def notify_badges(user: User, codes: list[str]) -> None:
    from .achievements import BADGE_INDEX

    for c in codes:
        b = BADGE_INDEX[c]
        _add(user, "badge", f"badge:{c}", f"Badge earned: {b.name}", b.description, "/dashboard")
    if codes:
        db.session.commit()


def unread(user: User, limit: int = 20) -> list[Notification]:
    return list(
        db.session.scalars(
            select(Notification)
            .where(Notification.user_id == user.id)
            .order_by(Notification.read_at.is_not(None), Notification.created_at.desc())
            .limit(limit)
        )
    )


def mark_read(user: User, ids: list[int] | None) -> None:
    q = update(Notification).where(Notification.user_id == user.id, Notification.read_at.is_(None))
    if ids:
        q = q.where(Notification.id.in_(ids))
    db.session.execute(q.values(read_at=utcnow()))
    db.session.commit()
