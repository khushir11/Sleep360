"""
Sleep360 – Smart Sleep & Attendance Intelligence System
Full-stack Flask application with HTML/CSS/JS frontend.

Run:  python app.py
Open: http://localhost:5000
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from flask import Flask, render_template, request, jsonify, session
from backend.database import init_db, add_student, get_student_by_email, get_all_students, \
    add_sleep_record, get_student_records, save_prediction, get_latest_prediction, \
    get_all_records, get_connection
from backend.analysis import (
    BehavioralData, analyse_student, age_group_stats,
    generate_insights, compute_sleep_metrics, research_stats
)
import json, os, random
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = "sleep360_secret_key_2024"

# ── Init DB ────────────────────────────────────────────────────────────────────
init_db()


# ══════════════════════════════════════════════════════════════════════════════
#  PAGE ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/")
def home():
    records = get_all_records()
    students = get_all_students()
    stats = age_group_stats(records) if records else {}
    return render_template("index.html",
        total_students=len(students),
        total_records=len(records),
        avg_sleep=stats.get("avg_sleep", 7.2),
        avg_attendance=stats.get("avg_attendance", 78.4),
        page="home"
    )

@app.route("/upload")
def upload():
    return render_template("upload.html", page="upload")

@app.route("/dashboard")
def dashboard():
    email = session.get("user_email")
    student = get_student_by_email(email) if email else None
    records = get_student_records(student["id"]) if student else []
    pred = get_latest_prediction(student["id"]) if student else None
    return render_template("dashboard.html",
        student=student, records=records, pred=pred, page="dashboard")

@app.route("/attendance")
def attendance():
    email = session.get("user_email")
    student = get_student_by_email(email) if email else None
    records = get_student_records(student["id"]) if student else []
    pred = get_latest_prediction(student["id"]) if student else None
    return render_template("attendance.html",
        student=student, records=records, pred=pred, page="attendance")

@app.route("/predictions")
def predictions():
    email = session.get("user_email")
    student = get_student_by_email(email) if email else None
    records = get_student_records(student["id"]) if student else []
    pred = get_latest_prediction(student["id"]) if student else None
    return render_template("predictions.html",
        student=student, records=records, pred=pred, page="predictions")

@app.route("/age-insights")
def age_insights():
    records = get_all_records()
    stats = age_group_stats(records) if records else {}
    return render_template("age_insights.html", stats=stats, page="age_insights")

@app.route("/recommendations")
def recommendations():
    email = session.get("user_email")
    student = get_student_by_email(email) if email else None
    records = get_student_records(student["id"]) if student else []
    pred = get_latest_prediction(student["id"]) if student else None
    return render_template("recommendations.html",
        student=student, records=records, pred=pred, page="recommendations")

@app.route("/research")
def research():
    records = get_all_records()
    stats = research_stats(records)
    return render_template("research.html", stats=stats, page="research")

@app.route("/about")
def about():
    return render_template("about.html", page="about")


# ══════════════════════════════════════════════════════════════════════════════
#  API ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/register", methods=["POST"])
def api_register():
    d = request.get_json(force=True)
    sid = add_student(d["name"], int(d["age"]), d["email"])
    s = get_student_by_email(d["email"])
    session["user_email"] = d["email"]
    return jsonify({"ok": True, "student": s})

@app.route("/api/login", methods=["POST"])
def api_login():
    d = request.get_json(force=True)
    s = get_student_by_email(d["email"])
    if not s:
        return jsonify({"ok": False, "error": "Not found"}), 404
    session["user_email"] = d["email"]
    return jsonify({"ok": True, "student": s})

@app.route("/api/logout", methods=["POST"])
def api_logout():
    session.pop("user_email", None)
    return jsonify({"ok": True})

@app.route("/api/submit", methods=["POST"])
def api_submit():
    email = session.get("user_email")
    if not email:
        return jsonify({"ok": False, "error": "Not logged in"}), 401

    student = get_student_by_email(email)
    if not student:
        return jsonify({"ok": False, "error": "Student not found"}), 404

    d = request.get_json(force=True)
    rec_id = add_sleep_record(student["id"], d)

    bdata = BehavioralData(
        sleep_duration=d["sleep_duration"],
        deep_sleep_percentage=d["deep_sleep_percentage"],
        sleep_timing=d["sleep_timing"],
        sleep_quality=d["sleep_quality"],
        study_hours=d.get("study_hours", 4),
        screen_time=d.get("screen_time", 4),
        physical_activity=d.get("physical_activity", 3),
        stress_level=d.get("stress_level", 5),
    )
    result = analyse_student(bdata)
    pred = {
        "predicted_attendance": result.predicted_attendance,
        "attendance_risk_level": result.attendance_risk.risk_level,
        "attendance_risk_score": result.attendance_risk.probability_score,
        "fatigue_risk_level":    result.fatigue_risk.risk_level,
        "fatigue_recommendation": result.fatigue_risk.recommendation,
        "sleep_score":           result.sleep_metrics.sleep_score,
    }
    save_prediction(student["id"], pred)
    insights = generate_insights(bdata, result)
    return jsonify({"ok": True, "result": pred, "insights": insights})

@app.route("/api/user-data")
def api_user_data():
    email = session.get("user_email")
    if not email:
        return jsonify({"ok": False})
    s = get_student_by_email(email)
    if not s:
        return jsonify({"ok": False})
    records = get_student_records(s["id"])
    pred = get_latest_prediction(s["id"])
    return jsonify({"ok": True, "student": s, "records": records, "pred": pred})

@app.route("/api/platform-stats")
def api_platform_stats():
    records = get_all_records()
    students = get_all_students()
    stats = age_group_stats(records) if records else {}
    stats["total_students"] = len(students)
    stats["total_records"] = len(records)
    return jsonify(stats)

@app.route("/api/age-group-data")
def api_age_group_data():
    records = get_all_records()
    groups = {}
    for r in records:
        age = r.get("age", 20)
        if age <= 17:    g = "14-17"
        elif age <= 19:  g = "17-19"
        elif age <= 22:  g = "20-22"
        else:            g = "23+"
        if g not in groups:
            groups[g] = {"sleep": [], "attendance": [], "stress": []}
        groups[g]["sleep"].append(r["sleep_duration"])
        if r["total_days"] > 0:
            groups[g]["attendance"].append(r["present_days"] / r["total_days"] * 100)
        groups[g]["stress"].append(r["stress_level"])

    result = {}
    for g, v in groups.items():
        result[g] = {
            "avg_sleep":      round(sum(v["sleep"])/len(v["sleep"]), 2) if v["sleep"] else 0,
            "avg_attendance": round(sum(v["attendance"])/len(v["attendance"]), 1) if v["attendance"] else 0,
            "avg_stress":     round(sum(v["stress"])/len(v["stress"]), 1) if v["stress"] else 0,
            "n": len(v["sleep"])
        }
    return jsonify(result)


if __name__ == "__main__":
    print("\n🌙 Sleep360 running at http://localhost:5000\n")
    app.run(debug=True, port=5000)
