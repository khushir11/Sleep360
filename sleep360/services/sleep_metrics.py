"""Sleep metrics: transparent, rule-based calculations (no ML here).

The Sleep Score is a documented heuristic, not a clinical measure. Its four
components are returned separately so the UI and the assistant can explain
exactly where points were lost.

Times are local naive datetimes. Bedtimes are compared on a "minutes after 18:00"
scale so that 23:30 and 00:30 are 60 minutes apart, not 23 hours.
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Protocol

SLEEP_LATENCY_MIN = 15  # typical time to fall asleep used by the bedtime planner
WIND_DOWN_MIN = 60
EVENING_ANCHOR_MIN = 18 * 60


class LogLike(Protocol):
    date: date
    bedtime: datetime
    wake_time: datetime
    quality: int


def duration_hours(log: LogLike) -> float:
    return (log.wake_time - log.bedtime).total_seconds() / 3600


def evening_minutes(dt: datetime | time) -> int:
    """Minutes after 18:00, wrapping past midnight (18:00 -> 0, 00:30 -> 390)."""
    m = dt.hour * 60 + dt.minute
    if m < EVENING_ANCHOR_MIN:
        m += 24 * 60
    return m - EVENING_ANCHOR_MIN


def minutes_to_clock(evening_min: float) -> str:
    total = int(round(evening_min + EVENING_ANCHOR_MIN)) % (24 * 60)
    return f"{total // 60:02d}:{total % 60:02d}"


def recommended_bedtime(target_wake: time, goal_hours: float) -> time:
    anchor = datetime.combine(date(2000, 1, 2), target_wake)
    bt = anchor - timedelta(hours=goal_hours, minutes=SLEEP_LATENCY_MIN)
    return bt.time()


def bedtime_plan(target_wake: time, goal_hours: float) -> dict:
    """Bedtime planner: goal-based bedtime plus 90-minute-cycle alternatives.

    Sleep cycles average roughly 90 minutes but vary between people and across the
    night, so cycle-based times are offered as approximate options only.
    """
    wake_dt = datetime.combine(date(2000, 1, 2), target_wake)
    bt = recommended_bedtime(target_wake, goal_hours)
    bt_dt = datetime.combine(date(2000, 1, 1) if bt > target_wake else date(2000, 1, 2), bt)
    cycles = []
    for n in (6, 5):
        c = wake_dt - timedelta(minutes=n * 90 + SLEEP_LATENCY_MIN)
        cycles.append({"cycles": n, "sleep_hours": n * 1.5, "bedtime": c.strftime("%H:%M")})
    return {
        "target_wake_time": target_wake.strftime("%H:%M"),
        "goal_hours": goal_hours,
        "bedtime": bt.strftime("%H:%M"),
        "wind_down_start": (bt_dt - timedelta(minutes=WIND_DOWN_MIN)).strftime("%H:%M"),
        "screens_off": (bt_dt - timedelta(minutes=30)).strftime("%H:%M"),
        "last_caffeine": (bt_dt - timedelta(hours=8)).strftime("%H:%M"),
        "latency_minutes": SLEEP_LATENCY_MIN,
        "cycle_options": cycles,
    }


@dataclass(frozen=True)
class ScoreBreakdown:
    duration: float  # /40
    regularity: float  # /25
    quality: float  # /20
    timing: float  # /15

    @property
    def total(self) -> float:
        return round(self.duration + self.regularity + self.quality + self.timing, 1)

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "components": {
                "duration": {"points": round(self.duration, 1), "max": 40},
                "regularity": {"points": round(self.regularity, 1), "max": 25},
                "quality": {"points": round(self.quality, 1), "max": 20},
                "timing": {"points": round(self.timing, 1), "max": 15},
            },
        }


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def sleep_score(log: LogLike, history: Sequence[LogLike], goal_hours: float, target_wake: time) -> ScoreBreakdown:
    """Score one night (0-100).

    * duration (40): full marks within [goal-0.5h, goal+1.5h]; linear to 0 at 4h short;
      mild penalty for > goal+2h.
    * regularity (25): bedtime deviation from the median of the previous 7 nights;
      0 min -> 25, >= 120 min -> 0. Full marks when there is no history yet.
    * quality (20): self-rated quality 1-10, scaled.
    * timing (15): how late bedtime is versus the planner's recommended bedtime;
      within 30 min -> 15, linear to 0 at 3h late. Going to bed early is not penalised.
    """
    dur = duration_hours(log)
    if dur < goal_hours - 0.5:
        d_pts = 40 * _clamp(1 - (goal_hours - 0.5 - dur) / 3.5)
    elif dur > goal_hours + 2:
        d_pts = 40 * _clamp(1 - (dur - goal_hours - 2) / 4, 0.6)
    else:
        d_pts = 40.0

    prev = [h for h in history if h.date < log.date][-7:]
    if prev:
        med = statistics.median(evening_minutes(h.bedtime) for h in prev)
        dev = abs(evening_minutes(log.bedtime) - med)
        r_pts = 25 * _clamp(1 - dev / 120)
    else:
        r_pts = 25.0

    q_pts = 20 * _clamp((log.quality - 1) / 9)

    rec = evening_minutes(recommended_bedtime(target_wake, goal_hours))
    late = evening_minutes(log.bedtime) - rec
    t_pts = 15.0 if late <= 30 else 15 * _clamp(1 - (late - 30) / 150)

    return ScoreBreakdown(d_pts, r_pts, q_pts, t_pts)


def window_stats(logs: Sequence[LogLike], goal_hours: float) -> dict:
    """Aggregate statistics over a window of logs (already filtered to the window)."""
    if not logs:
        return {"nights": 0}
    durs = [duration_hours(x) for x in logs]
    beds = [evening_minutes(x.bedtime) for x in logs]
    wakes = [x.wake_time.hour * 60 + x.wake_time.minute for x in logs]
    debt = sum(max(0.0, goal_hours - d) for d in durs)

    # Social jetlag: difference in sleep midpoint between free days (Fri/Sat nights,
    # i.e. waking Sat/Sun) and work days.
    def midpoint(x: LogLike) -> float:
        return evening_minutes(x.bedtime) + duration_hours(x) * 30

    free = [midpoint(x) for x in logs if x.date.weekday() >= 5]
    work = [midpoint(x) for x in logs if x.date.weekday() < 5]
    jetlag = abs(statistics.mean(free) - statistics.mean(work)) if free and work else None

    return {
        "nights": len(logs),
        "avg_duration": round(statistics.mean(durs), 2),
        "min_duration": round(min(durs), 2),
        "sleep_debt_hours": round(debt, 1),
        "avg_bedtime": minutes_to_clock(statistics.mean(beds)),
        "avg_wake_time": f"{int(statistics.mean(wakes)) // 60:02d}:{int(statistics.mean(wakes)) % 60:02d}",
        "bedtime_sd_minutes": round(statistics.pstdev(beds), 0) if len(beds) > 1 else 0.0,
        "social_jetlag_minutes": round(jetlag, 0) if jetlag is not None else None,
        "avg_quality": round(statistics.mean(x.quality for x in logs), 1),
        "nights_meeting_goal": sum(1 for d in durs if d >= goal_hours - 0.25),
        "late_nights": sum(1 for b in beds if b > 6 * 60 + 30),  # after 00:30
    }


def _avg_optional(logs: Sequence, attr: str) -> float | None:
    vals = [getattr(x, attr) for x in logs if getattr(x, attr, None) is not None]
    return round(statistics.mean(float(v) for v in vals), 1) if vals else None


def lifestyle_stats(logs: Sequence) -> dict:
    caffeine = [x.caffeine_after_2pm for x in logs if x.caffeine_after_2pm is not None]
    return {
        "avg_stress": _avg_optional(logs, "stress"),
        "avg_screen_minutes": _avg_optional(logs, "screen_minutes_before_bed"),
        "avg_exercise_minutes": _avg_optional(logs, "exercise_minutes"),
        "avg_sleepiness": _avg_optional(logs, "daytime_sleepiness"),
        "caffeine_late_days": sum(1 for c in caffeine if c),
        "caffeine_reported_days": len(caffeine),
    }


def logging_streak(dates: Sequence[date], today: date) -> int:
    """Consecutive days with a log, ending today (or yesterday if today isn't logged yet)."""
    s = set(dates)
    d = today if today in s else today - timedelta(days=1)
    n = 0
    while d in s:
        n += 1
        d -= timedelta(days=1)
    return n


def goal_streak(logs: Sequence[LogLike], goal_hours: float, today: date) -> int:
    by_date = {x.date: x for x in logs}
    d = today if today in by_date else today - timedelta(days=1)
    n = 0
    while d in by_date and duration_hours(by_date[d]) >= goal_hours - 0.25:
        n += 1
        d -= timedelta(days=1)
    return n
