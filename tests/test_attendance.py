from datetime import date

import pytest

from sleep360.services.attendance import classes_needed, remaining_classes, safe_skips


@pytest.mark.parametrize(
    "a,c,t,expected",
    [
        (45, 70, 75, 30),  # (45+x)/(70+x) >= .75 -> x >= 30
        (60, 80, 75, 0),  # exactly at target
        (0, 0, 75, 0),
        (9, 10, 100, None),  # 100% impossible after a miss
        (10, 10, 100, 0),
        (30, 40, 80, 10),
    ],
)
def test_classes_needed(a, c, t, expected):
    assert classes_needed(a, c, t) == expected
    if expected:
        assert (a + expected) / (c + expected) * 100 >= t
        assert (a + expected - 1) / (c + expected - 1) * 100 < t  # minimal


@pytest.mark.parametrize("a,c,t,expected", [(60, 70, 75, 10), (45, 70, 75, 0), (75, 100, 75, 0), (40, 40, 75, 13)])
def test_safe_skips(a, c, t, expected):
    s = safe_skips(a, c, t)
    assert s == expected
    if a / c * 100 < t:
        return
    assert a / (c + s) * 100 >= t
    assert a / (c + s + 1) * 100 < t


def test_remaining_classes():
    assert remaining_classes(3, date(2026, 1, 1), date(2026, 1, 29)) == 12
    assert remaining_classes(3, date(2026, 2, 1), date(2026, 1, 29)) == 0


def test_attendance_api_end_to_end(auth_client):
    sem = auth_client.post("/api/v1/semesters", json={"name": "S1", "start_date": "2026-08-01", "end_date": "2027-01-15"}).json
    sub = auth_client.post(
        "/api/v1/subjects",
        json={
            "semester_id": sem["id"],
            "name": "OS",
            "classes_per_week": 3,
            "initial_conducted": 20,
            "initial_attended": 14,
        },
    ).json
    assert sub["percentage"] == 70.0 and sub["status"] == "shortage" and sub["classes_needed"] == 4

    for d, st in [("2026-11-02", "present"), ("2026-11-03", "present"), ("2026-11-04", "cancelled")]:
        assert auth_client.post("/api/v1/attendance", json={"subject_id": sub["id"], "date": d, "status": st}).status_code == 201
    # re-marking the same slot updates instead of duplicating
    r = auth_client.post("/api/v1/attendance", json={"subject_id": sub["id"], "date": "2026-11-03", "status": "absent"})
    assert r.status_code == 200
    s = r.json["subject"]
    assert (s["attended"], s["conducted"]) == (15, 22)  # cancelled class not counted

    sim = auth_client.get(f"/api/v1/attendance/simulate?subject_id={sub['id']}&attend=5&miss=0").json
    assert sim["attended"] == 20 and sim["conducted"] == 27

    ov = auth_client.get("/api/v1/attendance").json
    assert ov["overall"]["subjects_at_risk"] == 1
    assert ov["monthly"][0]["month"] == "2026-11"


def test_subject_validation(auth_client):
    sem = auth_client.post("/api/v1/semesters", json={"name": "S1", "start_date": "2026-08-01", "end_date": "2027-01-15"}).json
    r = auth_client.post(
        "/api/v1/subjects", json={"semester_id": sem["id"], "name": "X", "initial_conducted": 5, "initial_attended": 9}
    )
    assert r.status_code == 422
    r = auth_client.post("/api/v1/semesters", json={"name": "bad", "start_date": "2026-08-01", "end_date": "2026-07-01"})
    assert r.status_code == 422


def test_custom_institution_target(auth_client):
    auth_client.patch("/api/v1/account", json={"attendance_target": 85})
    sem = auth_client.post("/api/v1/semesters", json={"name": "S1", "start_date": "2026-08-01", "end_date": "2027-01-15"}).json
    sub = auth_client.post(
        "/api/v1/subjects", json={"semester_id": sem["id"], "name": "Lab", "initial_conducted": 10, "initial_attended": 8}
    ).json
    assert sub["target"] == 85 and sub["status"] == "shortage"
