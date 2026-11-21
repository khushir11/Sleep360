"""Wellness assistant.

Architecture
------------
1. ``build_context`` turns the user's recent data into a compact, numeric summary.
   Only aggregates go to the LLM (no email, no raw notes), which keeps prompts small
   and limits what personal data leaves the server.
2. ``safety_check`` runs *before* any model call. Messages that suggest self-harm get
   a fixed, human-written response with crisis resources -- never an LLM improvisation.
3. ``AnthropicProvider`` calls Claude with the context in the system prompt. Any error
   (no key, timeout, rate limit, outage) falls through to...
4. ``FallbackProvider``: a deterministic intent matcher that answers common
   questions from the same context, so the feature always works.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import timedelta

from flask import current_app

from ..models import ChatMessage, User
from . import assessments, queries
from .attendance import summarize_subject
from .recommendations import generate as generate_recommendations
from .sleep_metrics import bedtime_plan, lifestyle_stats, window_stats

log = logging.getLogger(__name__)

CRISIS_PATTERNS = re.compile(
    r"\b(kill myself|suicid\w*|end (it|my life)|self[- ]?harm|hurt myself|want to die|don'?t want to (live|be alive)|no reason to live)\b",
    re.I,
)

CRISIS_RESPONSE = (
    "I'm really sorry you're feeling this way. You deserve support from a real person right now.\n\n"
    "- **India:** Tele-MANAS, free and 24/7: **14416** or 1-800-891-4416\n"
    "- **Emergency:** call **112**\n"
    "- Elsewhere: contact your local emergency number or a crisis line such as findahelpline.com\n\n"
    "If you can, reach out to someone you trust or your campus counselling service today. "
    "I'm an app assistant and can't provide crisis support, but I'm here if you want help with anything else."
)

SYSTEM_PROMPT = """You are Sleep360's wellness assistant for college students.

Rules:
- Ground every answer in the STUDENT DATA below. Quote their actual numbers when relevant.
- Be concise (under ~180 words), warm and practical. Prefer 2-4 concrete next steps.
- You give general sleep-hygiene and study-habit guidance. You are NOT a doctor: never diagnose
  (e.g. insomnia, sleep apnoea, depression). If symptoms sound persistent or severe (loud snoring with
  gasping, falling asleep while driving, weeks of poor sleep, low mood), recommend seeing a doctor or
  campus counsellor.
- The fatigue estimate comes from a model trained on SIMULATED data; describe it as a rough estimate.
- Attendance numbers are exact calculations; you may rely on them.
- If the data is missing for a question, say so and suggest what to log.
- Do not invent statistics or studies.

STUDENT DATA (JSON):
{context}
"""


def build_context(user: User) -> dict:
    today = queries.user_today(user)
    logs14 = queries.recent_logs(user, 14, today)
    week = [x for x in logs14 if x.date > today - timedelta(days=7)]
    prev = [x for x in logs14 if x.date <= today - timedelta(days=7)]
    latest = assessments.latest_two(user)
    cur = latest[0] if latest else None
    prv = latest[1] if len(latest) > 1 else None
    sem = queries.active_semester(user)
    subs = [summarize_subject(s, user.attendance_target, today) for s in queries.subjects_for(user, sem)]
    tasks = queries.open_tasks(user)[:6]
    pred = (cur.details.get("prediction") if cur else None) or {}
    return {
        "first_name": user.name.split()[0],
        "today": today.isoformat(),
        "goals": {
            "sleep_hours": user.sleep_goal_hours,
            "wake_time": user.target_wake_time.strftime("%H:%M"),
            "attendance_target_pct": user.attendance_target,
            "study_hours_week": user.study_goal_hours_week,
        },
        "bedtime_plan": bedtime_plan(user.target_wake_time, user.sleep_goal_hours),
        "last_7_days": window_stats(week, user.sleep_goal_hours) | lifestyle_stats(week),
        "previous_7_days": window_stats(prev, user.sleep_goal_hours) | lifestyle_stats(prev),
        "last_nights": [
            {
                "date": x.date.isoformat(),
                "hours": x.duration_hours,
                "bed": x.bedtime.strftime("%H:%M"),
                "quality": x.quality,
                "stress": x.stress,
            }
            for x in logs14[-5:]
        ],
        "latest_assessment": {
            "date": cur.date.isoformat(),
            "sleep_score": cur.sleep_score,
            "score_components": cur.details["score"]["components"],
            "fatigue_risk": cur.fatigue_level,
            "fatigue_probability": cur.fatigue_probability,
            "top_risk_factors": [c["label"] for c in pred.get("contributions", [])[:3] if c["impact"] > 0],
        }
        if cur
        else None,
        "change_since_previous": assessments.explain_change(cur, prv),
        "attendance": [
            {
                "subject": s.name,
                "pct": s.percentage,
                "target": s.target,
                "status": s.status,
                "classes_needed": s.classes_needed,
                "safe_skips": s.safe_skips,
                "projected_end_pct": s.projected_end,
            }
            for s in subs
        ],
        "upcoming_tasks": [
            {"title": t.title, "kind": t.kind.value, "due": t.due_at.strftime("%Y-%m-%d %H:%M") if t.due_at else None}
            for t in tasks
        ],
        "top_recommendations": [r["title"] for r in generate_recommendations(user)[:3]],
    }


def safety_check(message: str) -> str | None:
    return CRISIS_RESPONSE if CRISIS_PATTERNS.search(message) else None


@dataclass
class Reply:
    content: str
    provider: str


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, api_key: str, model: str, max_tokens: int):
        import anthropic  # imported lazily so the app runs without the package configured

        self.client = anthropic.Anthropic(api_key=api_key, timeout=25.0, max_retries=1)
        self.model = model
        self.max_tokens = max_tokens

    def reply(self, context: dict, history: list[ChatMessage], message: str) -> str:
        msgs = [{"role": m.role, "content": m.content} for m in history if m.role in ("user", "assistant")]
        # The API requires alternating roles starting with "user"
        while msgs and msgs[0]["role"] != "user":
            msgs.pop(0)
        msgs.append({"role": "user", "content": message})
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=SYSTEM_PROMPT.format(context=json.dumps(context, default=str)),
            messages=msgs,
        )
        text = "".join(getattr(b, "text", "") for b in resp.content).strip()
        if not text:
            raise RuntimeError("Empty response from model")
        return text


class FallbackProvider:
    """Deterministic, data-grounded answers for common intents."""

    name = "fallback"

    INTENTS = [
        ("why", r"\b(why|drop|dropped|lower|changed?|went down|went up|increase)\b"),
        ("bedtime", r"\b(bedtime|when should i (sleep|go to bed)|what time.*(sleep|bed)|wake)\b"),
        ("attendance", r"\b(attendance|bunk|skip|miss(ed)? class|classes|lecture|75)\b"),
        ("exam", r"\b(exam|test|all[- ]?nighter|cram)\b"),
        ("stress", r"\b(stress|anxious|anxiety|overwhelm|pressure|worried)\b"),
        ("caffeine", r"\b(coffee|caffeine|tea|energy drink|red ?bull)\b"),
        ("nap", r"\b(nap|napping)\b"),
        ("screen", r"\b(phone|screen|instagram|reels|youtube|scroll)\b"),
        ("improve", r"\b(improve|better|tips?|help me sleep|fall asleep|insomnia|can'?t sleep)\b"),
        ("summary", r"\b(how am i|summary|overview|doing|progress|week)\b"),
    ]

    def reply(self, context: dict, history: list, message: str) -> str:
        m = message.lower()
        for intent, pat in self.INTENTS:
            if re.search(pat, m):
                return getattr(self, f"_{intent}")(context)
        return self._help(context)

    # each handler uses only numbers from the context
    def _week(self, c):
        return c["last_7_days"]

    def _summary(self, c):
        w = self._week(c)
        if not w.get("nights"):
            return "I don't have any sleep logs from the last week yet. Log last night and I can give you a proper summary."
        a = c["latest_assessment"] or {}
        lines = [
            f"**Last 7 days, {c['first_name']}:**",
            f"- Average sleep **{w['avg_duration']}h** (goal {c['goals']['sleep_hours']}h); {w['nights_meeting_goal']}/{w['nights']} nights met your goal",
            f"- Typical bedtime **{w['avg_bedtime']}**, varying by ±{w['bedtime_sd_minutes']:.0f} min",
            f"- Sleep debt: **{w['sleep_debt_hours']}h**",
        ]
        if a:
            lines.append(
                f"- Latest sleep score **{a['sleep_score']:.0f}/100**"
                + (f", fatigue risk **{a['fatigue_risk']}** (rough estimate)" if a.get("fatigue_risk") else "")
            )
        risky = [s for s in c["attendance"] if s["status"] in ("shortage", "critical")]
        if risky:
            lines.append(f"- Attendance below target in: {', '.join(s['subject'] for s in risky)}")
        if c["top_recommendations"]:
            lines.append(f"\nTop priority: **{c['top_recommendations'][0]}**.")
        return "\n".join(lines)

    def _why(self, c):
        ch = c["change_since_previous"]
        out = [ch["summary"]]
        for d in ch.get("drivers", [])[:3]:
            out.append(f"- {d['label'].capitalize()}: {'+' if d['delta'] > 0 else ''}{d['delta']} points")
        if ch.get("risk"):
            out.append(ch["risk"]["text"])
            if ch["risk"]["top_factors"]:
                out.append("Biggest factors pushing risk up: " + ", ".join(ch["risk"]["top_factors"]) + ".")
        return "\n".join(out)

    def _bedtime(self, c):
        p = c["bedtime_plan"]
        cyc = " or ".join(f"{o['bedtime']} ({o['sleep_hours']:g}h)" for o in p["cycle_options"])
        return (
            f"To wake at **{p['target_wake_time']}** with {p['goal_hours']:g}h of sleep, aim for lights out at "
            f"**{p['bedtime']}**.\n- Start winding down at {p['wind_down_start']}\n- Screens off by {p['screens_off']}\n"
            f"- Last caffeine around {p['last_caffeine']}\n\nIf you prefer to time sleep cycles (approximate): {cyc}."
        )

    def _attendance(self, c):
        subs = c["attendance"]
        if not subs:
            return "You haven't added any subjects yet. Add them on the Attendance page and I can tell you exactly how many classes you need or can skip."
        lines = []
        for s in subs:
            if s["pct"] is None:
                continue
            if s["status"] == "critical":
                lines.append(
                    f"- **{s['subject']}** {s['pct']:.1f}%: {s['target']:.0f}% isn't reachable this semester. Talk to your faculty advisor."
                )
            elif s["status"] == "shortage":
                lines.append(
                    f"- **{s['subject']}** {s['pct']:.1f}%: attend the next **{s['classes_needed']}** classes to reach {s['target']:.0f}%"
                )
            else:
                lines.append(
                    f"- **{s['subject']}** {s['pct']:.1f}%: you can miss **{s['safe_skips']}** and stay above {s['target']:.0f}%"
                )
        return "Here's where you stand:\n" + "\n".join(lines)

    def _exam(self, c):
        p = c["bedtime_plan"]
        ex = [t for t in c["upcoming_tasks"] if t["kind"] == "exam"]
        head = f"You have **{ex[0]['title']}** due {ex[0]['due']}. " if ex else ""
        return (
            head + "Sleep after studying helps lock in what you learned, so an all-nighter usually backfires.\n"
            f"- Spread review over the next few days (the Planner does this automatically)\n"
            f"- Finish your last review by {p['wind_down_start']} and sleep at {p['bedtime']}\n"
            "- On exam morning, do a short recall session instead of new material"
        )

    def _stress(self, c):
        s = c["last_7_days"].get("avg_stress")
        head = f"Your average stress this week is **{s}/10**. " if s is not None else ""
        extra = (
            "That's high. Please consider talking to your campus counsellor; Tele-MANAS (14416) is also free and 24/7 in India.\n"
            if s is not None and s >= 8
            else ""
        )
        return (
            head + extra + "A few things that reliably help:\n- Write tomorrow's to-do list before bed to offload worries\n"
            "- 5 minutes of slow breathing (longer exhale than inhale)\n- Break study into 50-minute blocks with real breaks\n"
            "- 20-30 minutes of movement during the day"
        )

    def _caffeine(self, c):
        p = c["bedtime_plan"]
        n = c["last_7_days"].get("caffeine_late_days", 0)
        return (
            f"Caffeine stays in your system for hours (half-life ~5h). With a {p['bedtime']} bedtime, try to stop around "
            f"**{p['last_caffeine']}**." + (f" You had caffeine after 2pm on {n} day(s) this week." if n else "")
        )

    def _nap(self, c):
        return (
            "Naps can help if you keep them **short (10–20 min)** and **before ~3pm**. Longer or later naps make it harder "
            f"to fall asleep at your {c['bedtime_plan']['bedtime']} bedtime."
        )

    def _screen(self, c):
        s = c["last_7_days"].get("avg_screen_minutes")
        head = f"You're averaging **{s:.0f} min** of screens before bed. " if s is not None else ""
        return (
            head + f"Try a 'screens off' time of {c['bedtime_plan']['screens_off']}, charge your phone across the room, "
            "and switch on Do Not Disturb when your wind-down starts."
        )

    def _improve(self, c):
        recs = c["top_recommendations"]
        if recs:
            return (
                "Based on your data, I'd focus on:\n"
                + "\n".join(f"{i + 1}. {r}" for i, r in enumerate(recs))
                + "\n\nOpen the Insights page for the specific steps behind each one."
            )
        return (
            "Basics that work for most students: a fixed wake-up time every day, a 30–60 min wind-down, "
            "no caffeine after early afternoon, and a cool, dark room. Log a few nights and I'll tailor this to you."
        )

    def _help(self, c):
        return (
            "I can help with your sleep, attendance and study routine using your own data. Try asking:\n"
            "- *Why did my sleep score change?*\n- *What time should I go to bed?*\n"
            "- *How many classes can I skip?*\n- *How am I doing this week?*"
        )


def get_provider():
    key = current_app.config.get("ANTHROPIC_API_KEY")
    if key:
        try:
            return AnthropicProvider(key, current_app.config["ANTHROPIC_MODEL"], current_app.config["ASSISTANT_MAX_TOKENS"])
        except Exception as exc:  # package missing / bad config
            log.warning("Anthropic provider unavailable: %s", exc)
    return None


def respond(user: User, message: str, history: list[ChatMessage]) -> Reply:
    crisis = safety_check(message)
    if crisis:
        return Reply(crisis, "safety")
    context = build_context(user)
    provider = get_provider() if user.ai_assistant_enabled else None
    if provider is not None:
        try:
            return Reply(provider.reply(context, history[-10:], message), provider.name)
        except Exception as exc:
            log.warning("LLM call failed, using fallback: %s", exc)
    return Reply(FallbackProvider().reply(context, history, message), "fallback")
