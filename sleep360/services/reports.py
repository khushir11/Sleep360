"""Weekly wellness report (PDF via ReportLab) and full data export (JSON)."""

from __future__ import annotations

import io
from datetime import date, timedelta

from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.shapes import Drawing, Line, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from ..models import User
from . import queries
from .attendance import summarize_subject
from .dashboard import daily_series
from .recommendations import generate as generate_recommendations
from .sleep_metrics import lifestyle_stats, window_stats

INK = colors.HexColor("#1c1d29")
MUTED = colors.HexColor("#6b6f80")
ACCENT = colors.HexColor("#5b5bd6")
LINE = colors.HexColor("#e4e4ec")


def _sleep_chart(series: list[dict], goal: float) -> Drawing:
    d = Drawing(170 * mm, 55 * mm)
    ch = VerticalBarChart()
    ch.x, ch.y, ch.width, ch.height = 12 * mm, 8 * mm, 150 * mm, 42 * mm
    ch.data = [[s["duration"] or 0 for s in series]]
    ch.categoryAxis.categoryNames = [date.fromisoformat(s["date"]).strftime("%a") for s in series]
    ch.valueAxis.valueMin, ch.valueAxis.valueMax, ch.valueAxis.valueStep = 0, 11, 2
    ch.bars[0].fillColor = ACCENT
    ch.bars[0].strokeColor = None
    ch.categoryAxis.labels.fontName = ch.valueAxis.labels.fontName = "Helvetica"
    ch.categoryAxis.labels.fontSize = ch.valueAxis.labels.fontSize = 8
    d.add(ch)
    y = ch.y + ch.height * goal / 11
    d.add(Line(ch.x, y, ch.x + ch.width, y, strokeColor=colors.HexColor("#d4a72c"), strokeDashArray=[3, 2]))
    d.add(String(ch.x + ch.width - 30 * mm, y + 2, f"goal {goal:g}h", fontSize=7, fillColor=MUTED))
    return d


def weekly_pdf(user: User, end: date | None = None) -> bytes:
    end = end or queries.user_today(user)
    start = end - timedelta(days=6)
    logs = queries.sleep_logs(user, start, end)
    prev = queries.sleep_logs(user, start - timedelta(days=7), start - timedelta(days=1))
    w, pw = window_stats(logs, user.sleep_goal_hours), window_stats(prev, user.sleep_goal_hours)
    life = lifestyle_stats(logs)
    series = daily_series(user, 7, end)
    sem = queries.active_semester(user)
    subs = [summarize_subject(s, user.attendance_target, end) for s in queries.subjects_for(user, sem)]

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title="Sleep360 weekly report",
        author="Sleep360",
    )
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Title"], alignment=0, fontSize=20, textColor=INK, spaceAfter=2)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], fontSize=12.5, textColor=INK, spaceBefore=10, spaceAfter=4)
    body = ParagraphStyle("b", parent=ss["BodyText"], fontSize=9.5, leading=13, textColor=INK)
    small = ParagraphStyle("s", parent=body, fontSize=8, textColor=MUTED)

    def fmt(v, unit="", nd=1):
        return "—" if v is None else f"{v:.{nd}f}{unit}"

    def delta(a, b, unit="", good_up=True):
        if a is None or b is None:
            return ""
        d = a - b
        if abs(d) < 0.05:
            return "no change"
        arrow = "▲" if d > 0 else "▼"
        return f"{arrow} {abs(d):.1f}{unit}"

    story = [
        Paragraph("Sleep360 · Weekly wellness report", h1),
        Paragraph(f"{user.name} · {start:%d %b} – {end:%d %b %Y}", small),
        Spacer(1, 8),
    ]
    if user.is_demo:
        story.append(Paragraph("<b>Demo account:</b> all data in this report is generated sample data.", small))

    if not logs:
        story.append(Paragraph("No sleep was logged this week.", body))
    else:
        kpi = [
            ["Average sleep", "Sleep debt", "Bedtime variation", "Nights at goal", "Avg quality"],
            [
                fmt(w.get("avg_duration"), "h", 2),
                fmt(w.get("sleep_debt_hours"), "h"),
                f"±{w.get('bedtime_sd_minutes', 0):.0f} min",
                f"{w['nights_meeting_goal']}/{w['nights']}",
                fmt(w.get("avg_quality"), "/10"),
            ],
            [
                delta(w.get("avg_duration"), pw.get("avg_duration"), "h"),
                delta(w.get("sleep_debt_hours"), pw.get("sleep_debt_hours"), "h"),
                "",
                "",
                delta(w.get("avg_quality"), pw.get("avg_quality")),
            ],
        ]
        t = Table(kpi, colWidths=[34 * mm] * 5)
        t.setStyle(
            TableStyle(
                [
                    ("FONT", (0, 0), (-1, 0), "Helvetica", 8),
                    ("TEXTCOLOR", (0, 0), (-1, 0), MUTED),
                    ("FONT", (0, 1), (-1, 1), "Helvetica-Bold", 14),
                    ("TEXTCOLOR", (0, 1), (-1, 1), INK),
                    ("FONT", (0, 2), (-1, 2), "Helvetica", 7.5),
                    ("TEXTCOLOR", (0, 2), (-1, 2), MUTED),
                    ("BOX", (0, 0), (-1, -1), 0.5, LINE),
                    ("INNERGRID", (0, 0), (-1, -1), 0.25, LINE),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        story += [
            t,
            Paragraph("Changes compared with the previous 7 days.", small),
            Paragraph("Sleep duration", h2),
            _sleep_chart(series, user.sleep_goal_hours),
        ]

        rows = [["Date", "Bed", "Wake", "Hours", "Quality", "Score", "Stress", "Screens"]]
        for s in series:
            rows.append(
                [
                    date.fromisoformat(s["date"]).strftime("%a %d"),
                    s["bedtime"] or "—",
                    s["wake_time"] or "—",
                    fmt(s["duration"], "", 2),
                    s["quality"] or "—",
                    fmt(s["score"], "", 0),
                    s["stress"] or "—",
                    f"{s['screen']}m" if s["screen"] is not None else "—",
                ]
            )
        dt = Table(rows, colWidths=[22 * mm, 18 * mm, 18 * mm, 18 * mm, 18 * mm, 18 * mm, 18 * mm, 20 * mm])
        dt.setStyle(
            TableStyle(
                [
                    ("FONT", (0, 0), (-1, -1), "Helvetica", 8.5),
                    ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8.5),
                    ("LINEBELOW", (0, 0), (-1, 0), 0.6, INK),
                    ("LINEBELOW", (0, 1), (-1, -1), 0.25, LINE),
                    ("ALIGN", (1, 0), (-1, -1), "CENTER"),
                ]
            )
        )
        story += [Paragraph("Night by night", h2), dt]
        life_line = []
        if life["avg_stress"] is not None:
            life_line.append(f"average stress {life['avg_stress']}/10")
        if life["avg_screen_minutes"] is not None:
            life_line.append(f"{life['avg_screen_minutes']:.0f} min of screens before bed")
        if life["avg_exercise_minutes"] is not None:
            life_line.append(f"{life['avg_exercise_minutes']:.0f} active min/day")
        if life_line:
            story.append(Paragraph("Lifestyle: " + ", ".join(life_line) + ".", body))

    if subs:
        rows = [["Subject", "Attended / held", "%", "Target", "Status", "Next step"]]
        for s in subs:
            step = (
                f"Attend next {s.classes_needed}"
                if s.status == "shortage"
                else "Talk to advisor"
                if s.status == "critical"
                else f"{s.safe_skips} safe skips"
            )
            rows.append(
                [
                    s.name[:28],
                    f"{s.attended}/{s.conducted}",
                    fmt(s.percentage, "%"),
                    f"{s.target:.0f}%",
                    s.status.replace("_", " "),
                    step,
                ]
            )
        at = Table(rows, colWidths=[46 * mm, 26 * mm, 18 * mm, 16 * mm, 22 * mm, 36 * mm])
        at.setStyle(
            TableStyle(
                [
                    ("FONT", (0, 0), (-1, -1), "Helvetica", 8.5),
                    ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8.5),
                    ("LINEBELOW", (0, 0), (-1, 0), 0.6, INK),
                    ("LINEBELOW", (0, 1), (-1, -1), 0.25, LINE),
                ]
            )
        )
        story += [Paragraph(f"Attendance · {sem.name}", h2), at]

    recs = generate_recommendations(user)[:4]
    if recs:
        story.append(Paragraph("Focus for next week", h2))
        for r in recs:
            story.append(Paragraph(f"<b>{r['title']}</b>: {r['actions'][0] if r['actions'] else r['body']}", body))
            story.append(Paragraph(f"Why: {r['why']}", small))
            story.append(Spacer(1, 3))

    story += [
        Spacer(1, 10),
        Paragraph(
            "Sleep360 provides general wellness information, not medical advice. The fatigue estimate comes from a model "
            "trained on simulated data. If sleep problems persist or affect daily life, talk to a doctor.",
            small,
        ),
    ]
    doc.build(story)
    return buf.getvalue()


def export_all(user: User) -> dict:
    """Everything we store about the user, in a portable format (data-portability right)."""
    return {
        "exported_at": queries.user_now(user).isoformat(),
        "profile": user.to_dict(),
        "sleep_logs": [x.to_dict() for x in queries.sleep_logs(user)],
        "semesters": [
            {
                **s.to_dict(),
                "subjects": [
                    {
                        "name": sub.name,
                        "code": sub.code,
                        "classes_per_week": sub.classes_per_week,
                        "target_override": sub.target_override,
                        "initial_conducted": sub.initial_conducted,
                        "initial_attended": sub.initial_attended,
                        "records": [r.to_dict() for r in sub.records],
                    }
                    for sub in s.subjects
                ],
            }
            for s in user.semesters
        ],
        "tasks": [t.to_dict() for t in user.tasks],
        "study_sessions": [s.to_dict() for s in user.study_sessions],
        "assessments": [
            {
                "date": a.date.isoformat(),
                "sleep_score": a.sleep_score,
                "fatigue_probability": a.fatigue_probability,
                "model_version": a.model_version,
            }
            for a in user.assessments
        ],
        "chat_messages": [m.to_dict() for m in user.chat_messages],
        "achievements": [{"code": a.code, "earned_at": a.earned_at.isoformat()} for a in user.achievements],
    }
