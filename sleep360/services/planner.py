"""Sleep-friendly study planner.

Algorithm (greedy, explainable)
-------------------------------
1. Study window for the day: default start (17:00 weekdays / 10:00 weekends, or
   "now" if later) until a **cutoff = recommended bedtime − 60 min wind-down**.
   Nothing is ever scheduled after the cutoff -- that's the "sleep-friendly" rule.
2. Daily capacity = min(window, max_daily_minutes). If last night's sleep was more
   than 1.5h under goal, capacity is reduced by 25% (tired study is low-yield and
   it protects tonight's sleep).
3. For each open task compute remaining work (estimate − minutes already logged
   against it) and today's share = remaining / days_left (exams and assignments
   are spread out rather than crammed). Overdue/today items take their full remainder.
4. Order by (overdue, days_left, priority) and pack into 50-minute focus blocks
   with 10-minute breaks (a Pomodoro-style rhythm).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from ..models import StudySession, Task, User
from .sleep_metrics import WIND_DOWN_MIN, duration_hours, recommended_bedtime

FOCUS_MIN = 50
BREAK_MIN = 10
MIN_BLOCK = 20
DEFAULT_MAX_DAILY = 240


@dataclass
class Allocation:
    task: Task
    minutes: int
    days_left: int
    remaining: int


def _round_up_quarter(dt: datetime) -> datetime:
    add = (15 - dt.minute % 15) % 15
    return (dt + timedelta(minutes=add)).replace(second=0, microsecond=0)


def remaining_minutes(task: Task, sessions: list[StudySession]) -> int:
    done = sum(s.duration_minutes for s in sessions if s.task_id == task.id)
    return max(0, task.estimated_minutes - done)


def build_plan(
    user: User,
    day: date,
    now: datetime,
    tasks: list[Task],
    sessions: list[StudySession],
    last_night_hours: float | None,
    start: time | None = None,
    max_daily_minutes: int = DEFAULT_MAX_DAILY,
) -> dict:
    notes: list[str] = []
    bed = recommended_bedtime(user.target_wake_time, user.sleep_goal_hours)
    bed_dt = datetime.combine(day if bed.hour >= 12 else day + timedelta(days=1), bed)
    cutoff = bed_dt - timedelta(minutes=WIND_DOWN_MIN)

    default_start = time(10, 0) if day.weekday() >= 5 else time(17, 0)
    win_start = datetime.combine(day, start or default_start)
    if day == now.date():
        win_start = max(win_start, _round_up_quarter(now))
    window = max(0, int((cutoff - win_start).total_seconds() // 60))

    capacity = min(window, max_daily_minutes)
    if last_night_hours is not None and last_night_hours < user.sleep_goal_hours - 1.5:
        capacity = int(capacity * 0.75)
        notes.append(
            f"You slept {last_night_hours:.1f}h last night, so today's plan is 25% lighter. "
            f"Aim to be in bed by {bed.strftime('%H:%M')}."
        )
    notes.append(f"Study stops at {cutoff.strftime('%H:%M')} so you can wind down before a {bed.strftime('%H:%M')} bedtime.")

    allocs: list[Allocation] = []
    for t in tasks:
        if t.done:
            continue
        rem = remaining_minutes(t, sessions)
        if rem <= 0:
            continue
        if t.due_at is None:
            days_left = 14
        else:
            days_left = (t.due_at.date() - day).days
        if days_left <= 0:
            share = rem
        else:
            share = math.ceil(rem / (days_left + (0 if t.kind.value == "exam" else 1)))
            share = max(share, min(rem, MIN_BLOCK + 5))
        allocs.append(Allocation(t, share, days_left, rem))
    allocs.sort(key=lambda a: (a.days_left > 0, a.days_left, a.task.priority))

    blocks: list[dict] = []
    cursor = win_start
    used = 0
    unscheduled = []
    focus_since_break = 0
    for a in allocs:
        need = a.minutes
        while need > 0:
            left = capacity - used
            if left < MIN_BLOCK:
                break
            if focus_since_break >= FOCUS_MIN:
                blocks.append(
                    {
                        "type": "break",
                        "start": cursor.strftime("%H:%M"),
                        "end": (cursor + timedelta(minutes=BREAK_MIN)).strftime("%H:%M"),
                        "title": "Break — stand up, water, no phone",
                    }
                )
                cursor += timedelta(minutes=BREAK_MIN)
                focus_since_break = 0
            chunk = min(need, FOCUS_MIN - focus_since_break, left)
            if chunk < MIN_BLOCK and need > chunk:
                focus_since_break = FOCUS_MIN  # force a break, then continue
                continue
            end = cursor + timedelta(minutes=chunk)
            if end > cutoff:
                break
            blocks.append(
                {
                    "type": "focus",
                    "start": cursor.strftime("%H:%M"),
                    "end": end.strftime("%H:%M"),
                    "minutes": chunk,
                    "task_id": a.task.id,
                    "title": a.task.title,
                    "kind": a.task.kind.value,
                    "subject": a.task.subject.name if a.task.subject else None,
                    "due_in_days": a.days_left if a.task.due_at else None,
                }
            )
            cursor = end
            used += chunk
            need -= chunk
            focus_since_break += chunk
        if need > 0:
            unscheduled.append({"task_id": a.task.id, "title": a.task.title, "minutes": need, "overdue": a.days_left < 0})

    if blocks:
        blocks.append(
            {
                "type": "wind_down",
                "start": cutoff.strftime("%H:%M"),
                "end": bed.strftime("%H:%M"),
                "title": "Wind down — lights low, screens off 30 min before bed",
            }
        )
    if unscheduled:
        notes.append(
            "Some work didn't fit before your study cutoff. Consider starting earlier or adjusting estimates "
            "rather than staying up late."
        )
    if not allocs:
        notes.append("No open tasks. Add assignments or exams to get a plan.")

    return {
        "date": day.isoformat(),
        "window": {"start": win_start.strftime("%H:%M"), "cutoff": cutoff.strftime("%H:%M"), "minutes": window},
        "capacity_minutes": capacity,
        "planned_minutes": used,
        "bedtime": bed.strftime("%H:%M"),
        "blocks": blocks,
        "unscheduled": unscheduled,
        "notes": notes,
    }


def productivity(user: User, sessions: list[StudySession], logs: list, today: date, days: int = 14) -> dict:
    """Study-hour tracking and (cautious) sleep/study relationship from the user's own data."""
    start = today - timedelta(days=days - 1)
    per_day = {start + timedelta(days=i): 0 for i in range(days)}
    by_subject: dict[str, int] = {}
    focus = []
    for s in sessions:
        d = s.started_at.date()
        if d in per_day:
            per_day[d] += s.duration_minutes
            name = s.subject.name if s.subject else "General"
            by_subject[name] = by_subject.get(name, 0) + s.duration_minutes
            if s.focus:
                focus.append(s.focus)
    week_start = today - timedelta(days=today.weekday())
    week_minutes = sum(m for d, m in per_day.items() if d >= week_start)

    corr = None
    sleep_by_date = {x.date: duration_hours(x) for x in logs}
    pairs = [(sleep_by_date[d], m) for d, m in per_day.items() if d in sleep_by_date]
    if len(pairs) >= 10:
        import statistics

        xs, ys = zip(*pairs, strict=True)
        if statistics.pstdev(xs) > 0 and statistics.pstdev(ys) > 0:
            r = statistics.correlation(xs, ys)
            corr = {
                "r": round(r, 2),
                "n": len(pairs),
                "note": "Correlation in your own data over a short period. It does not show cause and effect.",
            }
    return {
        "daily": [{"date": d.isoformat(), "minutes": m} for d, m in per_day.items()],
        "by_subject": [{"subject": k, "minutes": v} for k, v in sorted(by_subject.items(), key=lambda kv: -kv[1])],
        "week_hours": round(week_minutes / 60, 1),
        "week_goal_hours": user.study_goal_hours_week,
        "avg_focus": round(sum(focus) / len(focus), 1) if focus else None,
        "sleep_study_correlation": corr,
    }
