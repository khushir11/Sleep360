"""Planner, recommendations, assistant, notifications, reports, dashboard."""

from datetime import date, datetime, time, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from sleep360.services.planner import build_plan

from .conftest import night


def _user(**kw):
    return SimpleNamespace(target_wake_time=time(7, 0), sleep_goal_hours=8.0, study_goal_hours_week=20, **kw)


def _task(i, title, due, est, kind="assignment", prio=2):
    return SimpleNamespace(
        id=i,
        title=title,
        due_at=due,
        estimated_minutes=est,
        priority=prio,
        done=False,
        kind=SimpleNamespace(value=kind),
        subject=None,
    )


def test_planner_never_schedules_past_wind_down():
    day = date(2026, 11, 23)  # Monday
    now = datetime.combine(day, time(8, 0))
    tasks = [_task(1, "Huge", datetime.combine(day, time(23, 0)), 900, prio=1)]
    plan = build_plan(_user(), day, now, tasks, [], 8.0, max_daily_minutes=600)
    assert plan["window"]["cutoff"] == "21:45"
    focus = [b for b in plan["blocks"] if b["type"] == "focus"]
    assert focus and all(b["end"] <= "21:45" for b in focus)
    assert plan["unscheduled"] and plan["unscheduled"][0]["minutes"] > 0
    assert any(b["type"] == "break" for b in plan["blocks"])


def test_planner_spreads_work_and_lightens_after_short_sleep():
    day = date(2026, 11, 23)
    now = datetime.combine(day, time(8, 0))
    tasks = [_task(1, "Exam", datetime.combine(day + timedelta(days=4), time(10)), 400, kind="exam")]
    normal = build_plan(_user(), day, now, tasks, [], 8.0)
    tired = build_plan(_user(), day, now, tasks, [], 5.0)
    assert normal["planned_minutes"] == 100  # 400 min over 4 days
    assert tired["capacity_minutes"] < normal["capacity_minutes"]
    assert any("lighter" in n for n in tired["notes"])


def test_planner_api_and_study_sessions(auth_client):
    t = auth_client.post(
        "/api/v1/tasks",
        json={
            "title": "Essay",
            "estimated_minutes": 120,
            "due_at": (datetime.now() + timedelta(days=3)).isoformat(timespec="minutes"),
        },
    ).json
    s = auth_client.post(
        "/api/v1/study-sessions",
        json={
            "started_at": (datetime.now() - timedelta(hours=30)).isoformat(timespec="minutes"),
            "duration_minutes": 50,
            "task_id": t["id"],
            "focus": 4,
        },
    )
    assert s.status_code == 201
    tasks = auth_client.get("/api/v1/tasks").json["items"]
    assert tasks[0]["remaining_minutes"] == 70
    assert auth_client.get("/api/v1/planner?date=2026-11-23&start=09:00").status_code == 200
    r = auth_client.patch(f"/api/v1/tasks/{t['id']}", json={"done": True})
    assert r.json["done"] and r.json["completed_at"]
    assert auth_client.get("/api/v1/productivity").json["avg_focus"] == 4.0


def test_recommendations_trigger_on_users_own_numbers(auth_client):
    for i in range(6):
        auth_client.post(
            "/api/v1/sleep",
            json=night(i, bed="01:30", wake="07:00", quality=4, stress=9, screen_minutes_before_bed=90, caffeine_after_2pm=True),
        )
    ids = {r["id"]: r for r in auth_client.get("/api/v1/recommendations").json["items"]}
    assert {"short_sleep", "sleep_debt", "high_stress", "screen_time", "caffeine", "late_bedtime"} <= set(ids)
    assert "5.5h" in ids["short_sleep"]["why"]
    assert "14416" in " ".join(ids["high_stress"]["actions"])


def test_recommendations_need_data_for_new_user(auth_client):
    ids = [r["id"] for r in auth_client.get("/api/v1/recommendations").json["items"]]
    assert ids == ["need_data"]


def test_assistant_fallback_is_grounded(auth_client):
    auth_client.post("/api/v1/sleep", json=night(1, quality=8))
    auth_client.post("/api/v1/sleep", json=night(0, bed="01:00", quality=4))
    r = auth_client.post("/api/v1/assistant/messages", json={"message": "Why did my score drop?"})
    m = r.json["message"]
    assert r.status_code == 201 and m["provider"] == "fallback" and "dropped" in m["content"]
    r = auth_client.post("/api/v1/assistant/messages", json={"message": "what time should I sleep?"})
    assert "22:45" in r.json["message"]["content"]
    assert len(auth_client.get("/api/v1/assistant/messages").json["items"]) == 4


def test_assistant_crisis_message_never_reaches_llm(app, auth_client):
    app.config["ANTHROPIC_API_KEY"] = "sk-test"
    with patch("sleep360.services.assistant.AnthropicProvider") as prov:
        r = auth_client.post("/api/v1/assistant/messages", json={"message": "I want to kill myself"})
        prov.assert_not_called()
    assert r.json["message"]["provider"] == "safety" and "14416" in r.json["message"]["content"]


def test_assistant_uses_llm_with_context_and_falls_back_on_error(app, auth_client):
    auth_client.post("/api/v1/sleep", json=night(0, notes="secret diary"))
    app.config["ANTHROPIC_API_KEY"] = "sk-test"
    with patch("sleep360.services.assistant.AnthropicProvider") as prov:
        prov.return_value.name = "anthropic"
        prov.return_value.reply.return_value = "You slept 7.5h."
        r = auth_client.post("/api/v1/assistant/messages", json={"message": "how was last night?"})
        ctx = prov.return_value.reply.call_args.args[0]
    assert r.json["message"]["provider"] == "anthropic"
    assert "secret diary" not in str(ctx) and "a@example.com" not in str(ctx)  # privacy: no notes/email
    with patch("sleep360.services.assistant.AnthropicProvider") as prov:
        prov.return_value.reply.side_effect = TimeoutError("boom")
        r = auth_client.post("/api/v1/assistant/messages", json={"message": "how am I doing"})
    assert r.json["message"]["provider"] == "fallback"


def test_notifications_are_deduplicated(app, auth_client):
    from sleep360.models import User
    from sleep360.services.notifications import scan

    evening = datetime.now().replace(hour=19, minute=0)
    with app.app_context():
        u = User.query.one()
        first = scan(u, evening)
        assert first >= 1
        assert scan(u, evening) == 0
    items = auth_client.get("/api/v1/notifications").json
    assert items["unread"] == first
    auth_client.post("/api/v1/notifications/read", json={})
    assert auth_client.get("/api/v1/notifications").json["unread"] == 0


def test_dashboard_analytics_and_badges(auth_client):
    for i in range(8):
        auth_client.post("/api/v1/sleep", json=night(i, bed="22:45", wake="07:00", quality=8))
    d = auth_client.get("/api/v1/dashboard").json
    assert d["week"]["nights"] == 7 and d["achievements"]["streaks"]["logging"] == 8
    earned = {b["code"] for b in d["achievements"]["badges"] if b["earned"]}
    assert {"first_log", "streak_7", "goal_5", "consistent_week"} <= earned
    a = auth_client.get("/api/v1/analytics?days=14").json
    assert len(a["series"]) == 14 and a["summary"]["nights"] == 8


def test_pdf_report_and_export(auth_client):
    auth_client.post("/api/v1/sleep", json=night(0))
    r = auth_client.get("/api/v1/reports/weekly.pdf")
    assert r.status_code == 200 and r.data[:4] == b"%PDF" and r.mimetype == "application/pdf"
    e = auth_client.get("/api/v1/account/export").json
    assert e["profile"]["email"] == "a@example.com" and len(e["sleep_logs"]) == 1


def test_settings_change_recomputes_scores(auth_client):
    auth_client.post("/api/v1/sleep", json=night(0, bed="23:00", wake="06:00"))  # 7h
    before = auth_client.get("/api/v1/assessment/latest").json["assessment"]["score"]["components"]["duration"]["points"]
    auth_client.patch("/api/v1/account", json={"sleep_goal_hours": 7})
    after = auth_client.get("/api/v1/assessment/latest").json["assessment"]["score"]["components"]["duration"]["points"]
    assert after > before
    assert auth_client.patch("/api/v1/account", json={"timezone": "Mars/Base"}).status_code == 422


def test_pages_render(auth_client, client):
    for p in ["/dashboard", "/sleep", "/attendance", "/planner", "/insights", "/assistant", "/settings", "/model", "/privacy"]:
        assert auth_client.get(p).status_code == 200, p
