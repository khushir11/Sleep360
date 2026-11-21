"""Recommendation engine.

A small rule engine: each rule is a function ``(ctx) -> Recommendation | None``
registered with ``@rule``. Rules read a pre-computed context (``build_context``) so
they are cheap, pure and individually unit-testable. Every recommendation carries
``why`` (the user's own numbers that triggered it) and a general evidence note.

Guidance is general wellness advice drawn from mainstream sleep-hygiene sources
(e.g. AASM/SRS adult sleep-duration consensus, CDC sleep-hygiene guidance). It is not
medical advice and does not diagnose anything.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta

from ..models import User
from . import queries
from .attendance import summarize_subject
from .sleep_metrics import evening_minutes, lifestyle_stats, minutes_to_clock, recommended_bedtime, window_stats


@dataclass
class Recommendation:
    id: str
    category: str  # sleep | routine | digital | stress | activity | attendance | study | general
    priority: int  # 1 = act now, 2 = important, 3 = nice to have
    title: str
    body: str
    actions: list[str]
    why: str
    evidence: str = ""
    tone: str = "info"  # info | warning | critical | positive

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Context:
    user: User
    week: dict
    prev_week: dict
    life: dict
    prev_life: dict
    subjects: list = field(default_factory=list)
    attendance_recent_rate: float | None = None
    attendance_overall_rate: float | None = None
    upcoming_exams: list = field(default_factory=list)
    rec_bedtime: str = ""


RULES: list[Callable[[Context], Recommendation | None]] = []


def rule(fn):
    RULES.append(fn)
    return fn


def build_context(user: User) -> Context:
    today = queries.user_today(user)
    logs14 = queries.recent_logs(user, 14, today)
    week = [x for x in logs14 if x.date > today - timedelta(days=7)]
    prev = [x for x in logs14 if x.date <= today - timedelta(days=7)]
    sem = queries.active_semester(user)
    subs = [summarize_subject(s, user.attendance_target, today) for s in queries.subjects_for(user, sem)]

    recs = queries.attendance_records(user, sem)
    recent = [r for r in recs if r.date > today - timedelta(days=14) and r.status.value != "cancelled"]
    allc = [r for r in recs if r.status.value != "cancelled"]
    rate = lambda rs: (sum(r.status.value == "present" for r in rs) / len(rs) * 100) if rs else None  # noqa: E731

    exams = [
        t for t in queries.open_tasks(user) if t.kind.value == "exam" and t.due_at and 0 <= (t.due_at.date() - today).days <= 3
    ]
    return Context(
        user=user,
        week=window_stats(week, user.sleep_goal_hours),
        prev_week=window_stats(prev, user.sleep_goal_hours),
        life=lifestyle_stats(week),
        prev_life=lifestyle_stats(prev),
        subjects=subs,
        attendance_recent_rate=rate(recent) if len(recent) >= 5 else None,
        attendance_overall_rate=rate(allc),
        upcoming_exams=exams,
        rec_bedtime=recommended_bedtime(user.target_wake_time, user.sleep_goal_hours).strftime("%H:%M"),
    )


# ── sleep ────────────────────────────────────────────────────────────────
@rule
def need_data(c: Context):
    if c.week.get("nights", 0) < 3:
        return Recommendation(
            "need_data",
            "general",
            2,
            "Log a few more nights",
            "Personalised advice needs at least 3 nights from the past week. It takes about 20 seconds a day.",
            ["Log last night's sleep now", "Set your wake-up time in Settings so bedtime advice fits you"],
            f"{c.week.get('nights', 0)} night(s) logged in the last 7 days.",
        )


@rule
def short_sleep(c: Context):
    avg, goal = c.week.get("avg_duration"), c.user.sleep_goal_hours
    if c.week.get("nights", 0) >= 3 and avg is not None and avg < goal - 1:
        return Recommendation(
            "short_sleep",
            "sleep",
            1,
            "You're consistently sleeping less than you need",
            f"You averaged {avg:.1f}h against a goal of {goal:.1f}h. Expert consensus recommends at least 7 hours "
            "for adults; regularly getting less is linked with poorer attention, mood and memory.",
            [
                f"Move bedtime 20–30 minutes earlier this week (aim for {c.rec_bedtime})",
                "Keep the same wake-up time, including weekends",
                "Protect the last hour before bed from studying",
            ],
            f"7-day average {avg:.1f}h; {c.week['nights_meeting_goal']}/{c.week['nights']} nights met your goal.",
            "AASM/SRS consensus statement on adult sleep duration (2015).",
            "warning",
        )


@rule
def sleep_debt(c: Context):
    debt = c.week.get("sleep_debt_hours", 0)
    if debt >= 5:
        return Recommendation(
            "sleep_debt",
            "sleep",
            1,
            f"About {debt:.0f} hours of sleep debt this week",
            "Sleep debt is best repaid gradually. A huge weekend lie-in shifts your body clock and makes Monday harder.",
            [
                "Add 30–60 minutes per night over the next few nights",
                "If you nap, keep it under 20–30 minutes and before 3pm",
                "Avoid sleeping in more than ~1 hour past your usual wake time",
            ],
            f"Total shortfall against your {c.user.sleep_goal_hours:.1f}h goal over {c.week['nights']} nights: {debt:.1f}h.",
            "General sleep-hygiene guidance (CDC, NHS).",
            "warning",
        )


@rule
def irregular_schedule(c: Context):
    sd = c.week.get("bedtime_sd_minutes")
    if c.week.get("nights", 0) >= 4 and sd is not None and sd > 60:
        return Recommendation(
            "irregular_schedule",
            "routine",
            2,
            "Your bedtime varies a lot",
            "Irregular sleep timing is associated with worse daytime alertness even when total sleep is similar. "
            "A fixed wake-up time is the most effective anchor.",
            [
                "Pick one wake-up time and keep it 7 days a week",
                f"Aim to be in bed within 30 minutes of {c.rec_bedtime}",
                "Start the Consistency streak on your dashboard",
            ],
            f"Your bedtime varied by ±{sd:.0f} minutes this week.",
            "Research on sleep regularity and circadian alignment.",
        )


@rule
def social_jetlag(c: Context):
    sj = c.week.get("social_jetlag_minutes")
    if sj is not None and sj >= 90:
        return Recommendation(
            "social_jetlag",
            "routine",
            2,
            "Weekend 'jet lag'",
            "Your sleep shifts significantly on weekends, which is like flying across time zones every Friday and back every Monday.",
            ["Keep weekend wake-up within an hour of weekdays", "Get daylight soon after waking on weekends"],
            f"Sleep midpoint differs by {sj:.0f} minutes between weekends and weekdays.",
            "Social jetlag literature (chronobiology).",
        )


@rule
def late_bedtime(c: Context):
    if c.week.get("nights", 0) < 3:
        return None
    rec = evening_minutes(recommended_bedtime(c.user.target_wake_time, c.user.sleep_goal_hours))
    avg = c.week["avg_bedtime"]
    avg_min = evening_minutes(datetime.strptime(avg, "%H:%M"))
    if avg_min - rec > 60:
        return Recommendation(
            "late_bedtime",
            "sleep",
            2,
            "Bedtime is later than your schedule allows",
            f"To wake at {c.user.target_wake_time.strftime('%H:%M')} with {c.user.sleep_goal_hours:.1f}h of sleep, "
            f"you need to be asleep by about {c.rec_bedtime}. You're averaging {avg}.",
            ["Set a wind-down alarm one hour before bedtime", "Shift bedtime earlier by 15 minutes every two nights"],
            f"Average bedtime {avg} vs recommended {c.rec_bedtime} ({(avg_min - rec) / 60:.1f}h late).",
        )


@rule
def good_sleep(c: Context):
    w = c.week
    if w.get("nights", 0) >= 5 and w["nights_meeting_goal"] >= w["nights"] - 1 and (w.get("bedtime_sd_minutes") or 0) <= 45:
        return Recommendation(
            "good_sleep",
            "sleep",
            3,
            "Great week of sleep",
            "You're meeting your goal and keeping a steady schedule. This is the foundation for focus and memory.",
            ["Keep your current routine", "Plan ahead for exam weeks so this doesn't slip"],
            f"{w['nights_meeting_goal']}/{w['nights']} nights met your goal; bedtime varied ±{w['bedtime_sd_minutes']:.0f} min.",
            tone="positive",
        )


# ── lifestyle ────────────────────────────────────────────────────────────
@rule
def screen_time(c: Context):
    cur, prev = c.life.get("avg_screen_minutes"), c.prev_life.get("avg_screen_minutes")
    rising = cur is not None and prev is not None and cur - prev >= 20
    if cur is not None and (cur >= 60 or (rising and cur >= 40)):
        return Recommendation(
            "screen_time",
            "digital",
            2,
            "Screens are eating into your wind-down",
            "Engaging content and bright screens late at night can delay sleep onset, mostly by keeping you up later.",
            [
                "Set a 'screens off' time 30 minutes before bed",
                "Charge your phone outside arm's reach",
                "Use focus/Do Not Disturb mode after your wind-down starts",
            ],
            f"Avg {cur:.0f} min of screens before bed" + (f", up from {prev:.0f} the week before." if rising else "."),
            "CDC sleep-hygiene guidance; evidence on blue light alone is mixed.",
        )


@rule
def caffeine(c: Context):
    n, reported = c.life.get("caffeine_late_days", 0), c.life.get("caffeine_reported_days", 0)
    if reported >= 3 and n >= 3:
        return Recommendation(
            "caffeine",
            "sleep",
            2,
            "Afternoon caffeine",
            "Caffeine's effects last several hours (its half-life is roughly 5 hours), so a 4pm coffee is still active at bedtime.",
            ["Switch to decaf or water after 2pm", "If you need an afternoon boost, try a 10-minute walk outside"],
            f"Caffeine after 2pm on {n} of {reported} reported days.",
            "Pharmacology of caffeine; sleep-hygiene guidance.",
        )


@rule
def stress(c: Context):
    s = c.life.get("avg_stress")
    if s is None:
        return None
    if s >= 8:
        return Recommendation(
            "high_stress",
            "stress",
            1,
            "Stress has been very high",
            "Sustained high stress makes sleep harder and is worth talking about. Your college counselling service "
            "is a good first step, and you don't need to be in crisis to use it.",
            [
                "Reach out to your campus counsellor or someone you trust",
                "Try a 5-minute breathing exercise (slow exhale) before bed",
                "Write tomorrow's to-do list before bed to offload worries",
                "In India, Tele-MANAS (14416) offers free, 24/7 mental-health support",
            ],
            f"Average stress {s:.1f}/10 over the last week.",
            "General stress-management guidance; not a diagnosis.",
            "critical",
        )
    if s >= 6.5:
        return Recommendation(
            "stress",
            "stress",
            2,
            "Stress is creeping up",
            "Moderate stress is normal around deadlines, but it's a common reason students sleep later and worse.",
            [
                "Schedule short breaks in study sessions (the planner adds them for you)",
                "Do 20–30 minutes of physical activity most days",
                "Keep a consistent wind-down routine",
            ],
            f"Average stress {s:.1f}/10 over the last week.",
        )


@rule
def low_activity(c: Context):
    ex = c.life.get("avg_exercise_minutes")
    if ex is not None and ex < 20:
        return Recommendation(
            "low_activity",
            "activity",
            3,
            "Move a little more",
            "Regular physical activity is associated with better sleep quality. Even a brisk walk counts.",
            [
                "Walk to class or take the stairs",
                "Aim for ~30 minutes of activity on most days, finishing a few hours before bed",
            ],
            f"Average {ex:.0f} active minutes per day this week.",
            "WHO physical-activity guidelines.",
        )


# ── attendance & study ──────────────────────────────────────────────────
@rule
def attendance_shortage(c: Context):
    bad = [s for s in c.subjects if s.status in ("shortage", "critical")]
    if not bad:
        return None
    worst = sorted(bad, key=lambda s: s.percentage or 0)[0]
    lines = []
    for s in bad[:4]:
        if s.status == "critical":
            lines.append(
                f"{s.name}: {s.percentage:.1f}% — target {s.target:.0f}% is no longer reachable this semester; talk to your faculty advisor"
            )
        else:
            lines.append(
                f"{s.name}: {s.percentage:.1f}% — attend the next {s.classes_needed} classes in a row to reach {s.target:.0f}%"
            )
    return Recommendation(
        "attendance_shortage",
        "attendance",
        1,
        f"Attendance shortage in {len(bad)} subject(s)",
        "These subjects are below your institution's requirement. Recovering is mostly about not missing the next few classes.",
        lines + ["Check the planner: late nights before early classes are the most common cause of missed lectures"],
        f"Lowest: {worst.name} at {worst.percentage:.1f}% vs {worst.target:.0f}% required.",
        tone="critical",
    )


@rule
def attendance_warning(c: Context):
    warn = [s for s in c.subjects if s.status == "warning"]
    if warn:
        names = ", ".join(
            f"{s.name} ({s.percentage:.0f}%, {s.safe_skips} safe skip{'s' if s.safe_skips != 1 else ''})" for s in warn[:3]
        )
        return Recommendation(
            "attendance_warning",
            "attendance",
            2,
            "Close to the attendance limit",
            "You're above the requirement but with little margin left.",
            ["Save your remaining skips for illness or emergencies", f"At risk: {names}"],
            f"{len(warn)} subject(s) within 5 points of the target.",
            tone="warning",
        )


@rule
def attendance_declining(c: Context):
    r, o = c.attendance_recent_rate, c.attendance_overall_rate
    if r is not None and o is not None and r < o - 10:
        return Recommendation(
            "attendance_declining",
            "attendance",
            2,
            "Attendance is slipping",
            "You've attended noticeably fewer classes in the last two weeks than your semester average.",
            [
                "Look at which mornings you missed and compare them with your sleep log",
                "Set a bedtime reminder the night before early lectures",
            ],
            f"Last 14 days: {r:.0f}% vs semester {o:.0f}%.",
            tone="warning",
        )


@rule
def exam_sleep(c: Context):
    if c.upcoming_exams:
        e = c.upcoming_exams[0]
        return Recommendation(
            "exam_sleep",
            "study",
            1,
            f"Exam coming up: {e.title}",
            "Sleep after studying helps consolidate memory, so an all-nighter usually costs more than it gains.",
            [
                "Do your final review earlier in the evening",
                f"Keep your normal bedtime ({c.rec_bedtime}) the night before",
                "Use the planner's sleep-friendly schedule for the next few days",
            ],
            f"Due {e.due_at.strftime('%a %d %b, %H:%M')}.",
            "Research on sleep and memory consolidation.",
            "warning",
        )


def generate(user: User) -> list[dict]:
    ctx = build_context(user)
    out = []
    for r in RULES:
        rec = r(ctx)
        if rec:
            out.append(rec)
    if any(r.id == "need_data" for r in out):
        out = [r for r in out if r.category not in ("sleep", "routine")]  # too little data for sleep advice
    out.sort(key=lambda r: (r.priority, r.tone != "critical"))
    return [r.to_dict() for r in out]


__all__ = ["generate", "build_context", "RULES", "Recommendation", "Context", "minutes_to_clock"]
