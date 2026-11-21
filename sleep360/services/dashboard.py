"""Aggregates for the dashboard and analytics pages (one round-trip per page)."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import select

from ..extensions import db
from ..models import RiskAssessment, User
from . import assessments, queries
from .achievements import evaluate as evaluate_achievements
from .attendance import overall, summarize_subject, weekly_trend
from .notifications import notify_badges
from .planner import productivity
from .recommendations import generate as generate_recommendations
from .sleep_metrics import bedtime_plan, duration_hours, lifestyle_stats, window_stats


def daily_series(user: User, days: int, end: date) -> list[dict]:
    logs = {x.date: x for x in queries.recent_logs(user, days, end)}
    ras = {
        r.date: r
        for r in db.session.scalars(
            select(RiskAssessment).where(RiskAssessment.user_id == user.id, RiskAssessment.date > end - timedelta(days=days))
        )
    }
    out = []
    for i in range(days):
        d = end - timedelta(days=days - 1 - i)
        x, r = logs.get(d), ras.get(d)
        out.append(
            {
                "date": d.isoformat(),
                "duration": round(duration_hours(x), 2) if x else None,
                "bedtime": x.bedtime.strftime("%H:%M") if x else None,
                "wake_time": x.wake_time.strftime("%H:%M") if x else None,
                "quality": x.quality if x else None,
                "stress": x.stress if x else None,
                "screen": x.screen_minutes_before_bed if x else None,
                "sleepiness": x.daytime_sleepiness if x else None,
                "score": r.sleep_score if r else None,
                "fatigue": r.fatigue_probability if r else None,
            }
        )
    return out


def dashboard(user: User) -> dict:
    today = queries.user_today(user)
    logs7 = queries.recent_logs(user, 7, today)
    logs30 = queries.recent_logs(user, 30, today)
    sem = queries.active_semester(user)
    subs = [summarize_subject(s, user.attendance_target, today) for s in queries.subjects_for(user, sem)]
    latest = assessments.latest_two(user)
    cur = latest[0] if latest else None
    prev = latest[1] if len(latest) > 1 else None

    ach = evaluate_achievements(user, today)
    notify_badges(user, ach["new_badges"])

    tasks = queries.open_tasks(user)
    upcoming = [t.to_dict() for t in tasks if t.due_at and t.due_at.date() <= today + timedelta(days=7)][:6]
    now = datetime.combine(today, datetime.min.time())
    sessions = queries.study_sessions(user, now - timedelta(days=13))
    prod = productivity(user, sessions, logs30, today)

    logged_today = any(x.date == today for x in logs7)
    daily_goals = [
        {"id": "log", "label": "Log last night's sleep", "done": logged_today},
        {
            "id": "sleep_goal",
            "label": f"Sleep {user.sleep_goal_hours:g}h",
            "done": bool(
                logged_today and duration_hours([x for x in logs7 if x.date == today][0]) >= user.sleep_goal_hours - 0.25
            ),
        },
        {
            "id": "study",
            "label": f"Study {user.study_goal_hours_week / 7:.1f}h",
            "done": prod["daily"][-1]["minutes"] >= user.study_goal_hours_week / 7 * 60,
        },
    ]

    return {
        "user": {"name": user.name, "is_demo": user.is_demo, "sleep_goal_hours": user.sleep_goal_hours},
        "today": today.isoformat(),
        "assessment": assessments.assessment_dict(cur),
        "change": assessments.explain_change(cur, prev),
        "week": window_stats(logs7, user.sleep_goal_hours),
        "month": window_stats(logs30, user.sleep_goal_hours),
        "lifestyle": lifestyle_stats(logs7),
        "series": daily_series(user, 14, today),
        "attendance": {
            "semester": sem.to_dict() if sem else None,
            "overall": overall(subs),
            "subjects": [s.to_dict() for s in subs],
        },
        "recommendations": generate_recommendations(user)[:4],
        "achievements": ach,
        "bedtime_plan": bedtime_plan(user.target_wake_time, user.sleep_goal_hours),
        "upcoming_tasks": upcoming,
        "study": {"week_hours": prod["week_hours"], "week_goal_hours": prod["week_goal_hours"]},
        "daily_goals": daily_goals,
    }


def analytics(user: User, days: int = 30) -> dict:
    today = queries.user_today(user)
    days = max(7, min(days, 180))
    sem = queries.active_semester(user)
    records = queries.attendance_records(user, sem)
    logs = queries.recent_logs(user, days, today)
    sessions = queries.study_sessions(user, datetime.combine(today - timedelta(days=days - 1), datetime.min.time()))

    # weekday pattern
    by_wd: dict[int, list[float]] = {i: [] for i in range(7)}
    for x in logs:
        by_wd[x.date.weekday()].append(duration_hours(x))
    weekday = [
        {
            "weekday": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][i],
            "avg_duration": round(sum(v) / len(v), 2) if v else None,
            "n": len(v),
        }
        for i, v in by_wd.items()
    ]

    # week-over-week summaries
    weeks = []
    for w in range(days // 7):
        end = today - timedelta(days=7 * w)
        chunk = [x for x in logs if end - timedelta(days=6) <= x.date <= end]
        weeks.append({"week_ending": end.isoformat(), **window_stats(chunk, user.sleep_goal_hours), **lifestyle_stats(chunk)})
    weeks.reverse()

    return {
        "days": days,
        "series": daily_series(user, days, today),
        "weekday_pattern": weekday,
        "weeks": weeks,
        "summary": window_stats(logs, user.sleep_goal_hours),
        "attendance_weekly": weekly_trend(records, min(16, max(4, days // 7)), today),
        "study": productivity(user, sessions, logs, today, days=min(days, 60)),
    }
