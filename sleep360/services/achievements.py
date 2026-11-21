"""Streaks, badges and the 7-night consistency challenge."""

from __future__ import annotations

import statistics
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import func, select

from ..extensions import db
from ..models import Achievement, StudySession, Task, User, utcnow
from . import queries
from .attendance import summarize_subject
from .sleep_metrics import duration_hours, evening_minutes, goal_streak, logging_streak, recommended_bedtime


@dataclass
class Badge:
    code: str
    name: str
    description: str
    icon: str  # name of an inline SVG icon in the frontend sprite
    check: Callable[[dict], bool]


def _stats(user: User, today: date) -> dict:
    logs = queries.sleep_logs(user, today - timedelta(days=60), today)
    dates = [x.date for x in logs]
    last7 = [x for x in logs if x.date > today - timedelta(days=7)]
    sem = queries.active_semester(user)
    subs = [summarize_subject(s, user.attendance_target, today) for s in queries.subjects_for(user, sem)]
    tasks_done = db.session.scalar(select(func.count()).select_from(Task).where(Task.user_id == user.id, Task.done.is_(True)))
    study_min = db.session.scalar(
        select(func.coalesce(func.sum(StudySession.duration_minutes), 0)).where(StudySession.user_id == user.id)
    )
    return {
        "total_logs": len(user.sleep_logs),
        "log_streak": logging_streak(dates, today),
        "goal_streak": goal_streak(logs, user.sleep_goal_hours, today),
        "last7": last7,
        "goal": user.sleep_goal_hours,
        "subjects": subs,
        "tasks_done": tasks_done or 0,
        "study_minutes": study_min or 0,
        "challenge": consistency_challenge(user, logs, today),
    }


BADGES: list[Badge] = [
    Badge("first_log", "First Night", "Logged your first night of sleep", "moon", lambda s: s["total_logs"] >= 1),
    Badge("streak_7", "Week Streak", "Logged sleep 7 days in a row", "flame", lambda s: s["log_streak"] >= 7),
    Badge("streak_30", "Habit Formed", "Logged sleep 30 days in a row", "trophy", lambda s: s["log_streak"] >= 30),
    Badge("goal_5", "Well Rested", "Met your sleep goal 5 nights in a row", "battery", lambda s: s["goal_streak"] >= 5),
    Badge(
        "consistent_week",
        "Clockwork",
        "Completed the 7-night consistency challenge",
        "clock",
        lambda s: s["challenge"]["completed"],
    ),
    Badge(
        "attendance_safe",
        "Front Row",
        "Every subject at or above target (10+ classes each)",
        "check",
        lambda s: bool(s["subjects"]) and all(x.conducted >= 10 and x.status in ("safe", "warning") for x in s["subjects"]),
    ),
    Badge("tasks_10", "Task Crusher", "Completed 10 tasks", "list", lambda s: s["tasks_done"] >= 10),
    Badge("focus_10h", "Deep Work", "Logged 10 hours of focused study", "book", lambda s: s["study_minutes"] >= 600),
]
BADGE_INDEX = {b.code: b for b in BADGES}


def consistency_challenge(user: User, logs: list, today: date) -> dict:
    """In bed within ±30 min of your recommended bedtime for 7 consecutive nights."""
    rec = evening_minutes(recommended_bedtime(user.target_wake_time, user.sleep_goal_hours))
    by_date = {x.date: x for x in logs}
    d = today if today in by_date else today - timedelta(days=1)
    n = 0
    while d in by_date and abs(evening_minutes(by_date[d].bedtime) - rec) <= 30:
        n += 1
        d -= timedelta(days=1)
    return {"nights": min(n, 7), "target": 7, "completed": n >= 7, "window": "within 30 minutes of your recommended bedtime"}


def evaluate(user: User, today: date | None = None) -> dict:
    """Award any newly earned badges (idempotent) and return the full state."""
    today = today or queries.user_today(user)
    s = _stats(user, today)
    have = {a.code: a for a in user.achievements}
    new = []
    for b in BADGES:
        if b.code not in have and b.check(s):
            a = Achievement(user_id=user.id, code=b.code)
            db.session.add(a)
            have[b.code] = a
            new.append(b.code)
    if new:
        db.session.commit()

    last7 = s["last7"]
    beds = [evening_minutes(x.bedtime) for x in last7]
    return {
        "streaks": {"logging": s["log_streak"], "sleep_goal": s["goal_streak"]},
        "challenge": s["challenge"],
        "consistency_7d": round(max(0.0, 100 - statistics.pstdev(beds) / 1.2), 0) if len(beds) >= 3 else None,
        "goal_nights_7d": sum(1 for x in last7 if duration_hours(x) >= s["goal"] - 0.25),
        "badges": [
            {
                "code": b.code,
                "name": b.name,
                "description": b.description,
                "icon": b.icon,
                "earned": b.code in have,
                "earned_at": have[b.code].earned_at.isoformat(timespec="minutes")
                if b.code in have and have[b.code].earned_at
                else None,
            }
            for b in BADGES
        ],
        "new_badges": new,
        "_evaluated_at": utcnow().isoformat(timespec="seconds"),
    }
