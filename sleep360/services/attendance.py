"""Attendance calculations.

The arithmetic is deterministic and exact, which is what students need to make
decisions ("how many classes can I miss?"). Forecasts are simple and explicit:
remaining classes are estimated from the subject's weekly schedule and the
semester end date; the projection assumes the student keeps their recent
(28-day) attendance rate.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from ..models import AttendanceRecord, AttendanceStatus, Subject

RECENT_WINDOW_DAYS = 28


def percentage(attended: int, conducted: int) -> float | None:
    return round(attended / conducted * 100, 2) if conducted else None


def classes_needed(attended: int, conducted: int, target_pct: float) -> int | None:
    """Consecutive classes to attend to reach target. None if mathematically impossible (target 100% after a miss)."""
    t = target_pct / 100
    if conducted and attended / conducted >= t:
        return 0
    if t >= 1:
        return None if attended < conducted else 0
    # (A + x) / (C + x) >= t  ->  x >= (tC - A) / (1 - t)
    return max(0, math.ceil((t * conducted - attended) / (1 - t) - 1e-9))


def safe_skips(attended: int, conducted: int, target_pct: float) -> int:
    """Classes that can be missed in a row while staying at/above target."""
    t = target_pct / 100
    if t <= 0:
        return 10**6
    # A / (C + y) >= t  ->  y <= A/t - C
    return max(0, math.floor(attended / t - conducted + 1e-9))


def remaining_classes(classes_per_week: float, today: date, semester_end: date) -> int:
    days = (semester_end - today).days
    return max(0, math.floor(days / 7 * classes_per_week))


@dataclass
class SubjectSummary:
    id: int
    name: str
    code: str | None
    color: str
    target: float
    conducted: int
    attended: int
    percentage: float | None
    status: str
    classes_needed: int | None
    safe_skips: int
    remaining_classes: int
    max_achievable: float | None
    projected_end: float | None
    recent_rate: float | None
    classes_per_week: float
    initial_conducted: int = 0
    initial_attended: int = 0

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def summarize_subject(subject: Subject, default_target: float, today: date) -> SubjectSummary:
    recs = [r for r in subject.records if r.status != AttendanceStatus.cancelled and r.date <= today]
    conducted = subject.initial_conducted + len(recs)
    attended = subject.initial_attended + sum(1 for r in recs if r.status == AttendanceStatus.present)
    target = subject.target_override or default_target
    pct = percentage(attended, conducted)

    since = today - timedelta(days=RECENT_WINDOW_DAYS)
    recent = [r for r in recs if r.date > since]
    recent_rate = sum(1 for r in recent if r.status == AttendanceStatus.present) / len(recent) if len(recent) >= 3 else None
    rate = recent_rate if recent_rate is not None else (attended / conducted if conducted else 1.0)

    remaining = remaining_classes(subject.classes_per_week, today, subject.semester.end_date)
    final_total = conducted + remaining
    max_ach = percentage(attended + remaining, final_total)
    projected = round((attended + rate * remaining) / final_total * 100, 2) if final_total else None

    needed = classes_needed(attended, conducted, target)
    if pct is None:
        status = "no_data"
    elif max_ach is not None and max_ach < target:
        status = "critical"  # cannot reach target even attending every remaining class
    elif pct < target:
        status = "shortage"
    elif pct < target + 5:
        status = "warning"
    else:
        status = "safe"

    return SubjectSummary(
        id=subject.id,
        name=subject.name,
        code=subject.code,
        color=subject.color,
        target=target,
        conducted=conducted,
        attended=attended,
        percentage=pct,
        status=status,
        classes_needed=needed,
        safe_skips=safe_skips(attended, conducted, target) if pct is not None else 0,
        remaining_classes=remaining,
        max_achievable=max_ach,
        projected_end=projected,
        recent_rate=round(recent_rate * 100, 1) if recent_rate is not None else None,
        classes_per_week=subject.classes_per_week,
        initial_conducted=subject.initial_conducted,
        initial_attended=subject.initial_attended,
    )


def overall(summaries: list[SubjectSummary]) -> dict:
    c = sum(s.conducted for s in summaries)
    a = sum(s.attended for s in summaries)
    return {
        "conducted": c,
        "attended": a,
        "percentage": percentage(a, c),
        "subjects_at_risk": sum(1 for s in summaries if s.status in ("shortage", "critical")),
        "subjects_warning": sum(1 for s in summaries if s.status == "warning"),
    }


def weekly_trend(records: list[AttendanceRecord], weeks: int, today: date) -> list[dict]:
    """Attendance % per ISO week for the last ``weeks`` weeks (cumulative-free, per-week rate)."""
    start = today - timedelta(days=today.weekday()) - timedelta(weeks=weeks - 1)
    buckets: dict[date, list[int]] = defaultdict(lambda: [0, 0])
    for r in records:
        if r.status == AttendanceStatus.cancelled or r.date < start or r.date > today:
            continue
        wk = r.date - timedelta(days=r.date.weekday())
        buckets[wk][1] += 1
        if r.status == AttendanceStatus.present:
            buckets[wk][0] += 1
    out = []
    for i in range(weeks):
        wk = start + timedelta(weeks=i)
        a, c = buckets.get(wk, (0, 0))
        out.append({"week_start": wk.isoformat(), "attended": a, "conducted": c, "percentage": percentage(a, c)})
    return out


def monthly_history(records: list[AttendanceRecord]) -> list[dict]:
    buckets: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for r in records:
        if r.status == AttendanceStatus.cancelled:
            continue
        key = r.date.strftime("%Y-%m")
        buckets[key][1] += 1
        if r.status == AttendanceStatus.present:
            buckets[key][0] += 1
    return [
        {"month": k, "attended": v[0], "conducted": v[1], "percentage": percentage(v[0], v[1])}
        for k, v in sorted(buckets.items())
    ]
