from datetime import date, datetime, time
from types import SimpleNamespace

from sleep360.services.sleep_metrics import bedtime_plan, evening_minutes, sleep_score, window_stats

from .conftest import night


def L(d, bed, wake, q=7):
    """Build a log-like object for night ending on date d."""
    bh, bm = map(int, bed.split(":"))
    wh, wm = map(int, wake.split(":"))
    from datetime import timedelta

    b = datetime.combine(d - timedelta(days=1) if bh >= 12 else d, time(bh, bm))
    return SimpleNamespace(
        date=d,
        bedtime=b,
        wake_time=datetime.combine(d, time(wh, wm)),
        quality=q,
        stress=None,
        screen_minutes_before_bed=None,
        caffeine_after_2pm=None,
        exercise_minutes=None,
    )


def test_evening_minutes_wraps_midnight():
    assert evening_minutes(time(18, 0)) == 0
    assert evening_minutes(time(23, 30)) == 330
    assert evening_minutes(time(0, 30)) == 390
    assert evening_minutes(time(0, 30)) - evening_minutes(time(23, 30)) == 60


def test_perfect_night_scores_100():
    d = date(2026, 11, 10)
    log = L(d, "22:45", "07:00", q=10)
    s = sleep_score(log, [], 8.0, time(7, 0))
    assert s.total == 100


def test_short_late_irregular_night_loses_points_in_right_components():
    hist = [L(date(2026, 11, i), "23:00", "07:00") for i in range(1, 8)]
    bad = L(date(2026, 11, 8), "02:30", "07:00", q=4)
    s = sleep_score(bad, hist, 8.0, time(7, 0))
    assert s.duration < 20 and s.regularity == 0 and s.timing < 5
    assert s.total < 40


def test_window_stats_debt_and_variability():
    logs = [L(date(2026, 11, i), "23:00", "06:00") for i in range(2, 9)]  # 7h, goal 8 -> 1h debt/night
    w = window_stats(logs, 8.0)
    assert w["avg_duration"] == 7.0 and w["sleep_debt_hours"] == 7.0 and w["bedtime_sd_minutes"] == 0


def test_bedtime_plan():
    p = bedtime_plan(time(7, 0), 8.0)
    assert p["bedtime"] == "22:45" and p["wind_down_start"] == "21:45" and p["screens_off"] == "22:15"
    assert p["cycle_options"][0] == {"cycles": 6, "sleep_hours": 9.0, "bedtime": "21:45"}


def test_log_upsert_and_assessment(auth_client):
    r = auth_client.post("/api/v1/sleep", json=night(1, quality=8, stress=4))
    assert r.status_code == 201
    r = auth_client.post("/api/v1/sleep", json=night(0, bed="01:30", wake="07:00", quality=4, stress=8))
    assert r.status_code == 201
    body = r.json
    assert body["assessment"]["sleep_score"] < 70
    assert body["assessment"]["prediction"]["level"] in ("low", "moderate", "high")
    assert "dropped" in body["change"]["summary"]
    # same night again -> update, not duplicate
    r = auth_client.post("/api/v1/sleep", json=night(0, quality=9))
    assert r.status_code == 200 and r.json["created"] is False
    assert len(auth_client.get("/api/v1/sleep").json["items"]) == 2


def test_log_validation(auth_client):
    p = night(0)
    p["wake_time"], p["bedtime"] = p["bedtime"], p["wake_time"]
    assert auth_client.post("/api/v1/sleep", json=p).status_code == 422
    assert auth_client.post("/api/v1/sleep", json=night(0, quality=11)).status_code == 422
    assert auth_client.post("/api/v1/sleep", json=night(-2)).status_code == 422  # future
    assert auth_client.post("/api/v1/sleep", data="not json", content_type="application/json").status_code == 400


def test_delete_log_removes_assessment(auth_client):
    log = auth_client.post("/api/v1/sleep", json=night(0)).json["log"]
    assert auth_client.get("/api/v1/assessment/latest").json["assessment"]
    assert auth_client.delete(f"/api/v1/sleep/{log['id']}").status_code == 204
    assert auth_client.get("/api/v1/assessment/latest").json["assessment"] is None


def test_csv_import_pipeline(auth_client):
    csv = (
        b"Date,Bedtime,Wake Time,Sleep Score,Stress,Caffeine\n"
        b"2026-11-01,23:40,07:05,72,5,no\n"
        b"2026-11-02,00:30,07:00,55,6,yes\n"
        b"2026-11-02,00:45,07:10,60,6,yes\n"  # duplicate date -> last wins
        b"2026-11-03,07:00,06:00,80,4,no\n"  # would be 23h -> rejected
        b"2026-11-04,bad,07:00,70,4,no\n"  # unparseable
    )
    from io import BytesIO

    r = auth_client.post("/api/v1/sleep/import", data={"file": (BytesIO(csv), "sleep.csv")}, content_type="multipart/form-data")
    rep = r.json["report"]
    assert r.status_code == 200
    assert rep["created"] == 2 and rep["duplicates_in_file"] == 1 and rep["error_count"] == 2
    logs = {x["date"]: x for x in auth_client.get("/api/v1/sleep?start=2026-10-30&end=2026-11-05").json["items"]}
    assert logs["2026-11-02"]["bedtime"].endswith("00:45") and logs["2026-11-02"]["quality"] == 6
    assert logs["2026-11-02"]["source"] == "csv"
    # re-import without overwrite skips existing
    r = auth_client.post("/api/v1/sleep/import", data={"file": (BytesIO(csv), "sleep.csv")}, content_type="multipart/form-data")
    assert r.json["report"]["skipped_existing"] == 2


def test_csv_missing_columns(auth_client):
    from io import BytesIO

    r = auth_client.post(
        "/api/v1/sleep/import", data={"file": (BytesIO(b"foo,bar\n1,2\n"), "x.csv")}, content_type="multipart/form-data"
    )
    assert r.json["report"]["created"] == 0 and r.json["report"]["error_count"] == 1
