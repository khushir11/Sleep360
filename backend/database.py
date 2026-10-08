"""
Sleep360 – SQLite Database Layer
"""
import sqlite3
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent.parent / "data" / "sleep360.db"

def get_connection():
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                age INTEGER NOT NULL,
                email TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS sleep_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                sleep_duration REAL NOT NULL,
                deep_sleep_percentage REAL NOT NULL DEFAULT 18,
                sleep_timing INTEGER NOT NULL DEFAULT 0,
                sleep_quality REAL NOT NULL DEFAULT 7,
                study_hours REAL NOT NULL DEFAULT 4,
                screen_time REAL NOT NULL DEFAULT 4,
                physical_activity REAL NOT NULL DEFAULT 3,
                stress_level REAL NOT NULL DEFAULT 5,
                present_days INTEGER NOT NULL DEFAULT 50,
                total_days INTEGER NOT NULL DEFAULT 60,
                late_arrivals INTEGER DEFAULT 0,
                missed_first_hour INTEGER DEFAULT 0,
                age_group TEXT DEFAULT '20-22',
                record_date DATE DEFAULT (date('now')),
                FOREIGN KEY (student_id) REFERENCES students(id)
            );
            CREATE TABLE IF NOT EXISTS predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                predicted_attendance REAL NOT NULL,
                attendance_risk_level TEXT NOT NULL,
                attendance_risk_score REAL NOT NULL,
                fatigue_risk_level TEXT NOT NULL,
                fatigue_recommendation TEXT NOT NULL,
                sleep_score REAL NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (student_id) REFERENCES students(id)
            );
        """)
    _seed_demo_data()

def _seed_demo_data():
    """Add demo students if DB is empty."""
    with get_connection() as conn:
        if conn.execute("SELECT COUNT(*) FROM students").fetchone()[0] > 0:
            return
    demos = [
        ("Ananya Sharma", 20, "ananya@demo.com", 5.5, 12, 1, 5.0, 6.0, 7.0, 1.0, 8.0, 45, 70, 2, 3, "20-22"),
        ("Rahul Verma",   21, "rahul@demo.com",  7.5, 22, 0, 8.0, 5.0, 3.0, 5.0, 4.0, 65, 70, 0, 0, "20-22"),
        ("Priya Nair",    19, "priya@demo.com",  6.0, 16, 1, 6.0, 7.0, 5.0, 2.5, 6.5, 52, 70, 1, 1, "17-19"),
        ("Dev Kapoor",    22, "dev@demo.com",    8.0, 24, 0, 9.0, 4.5, 2.5, 6.0, 3.0, 68, 70, 0, 0, "20-22"),
        ("Sneha Reddy",   18, "sneha@demo.com",  5.0, 10, 1, 4.5, 8.0, 8.0, 0.5, 9.0, 40, 70, 4, 5, "17-19"),
        ("Arjun Mehta",   23, "arjun@demo.com",  7.0, 20, 0, 7.5, 5.5, 3.5, 4.0, 5.5, 60, 70, 1, 0, "23+"),
        ("Kavya Singh",   17, "kavya@demo.com",  6.5, 18, 1, 6.5, 6.0, 4.0, 3.0, 7.0, 55, 70, 2, 2, "14-17"),
        ("Rohan Das",     21, "rohan@demo.com",  4.5, 8,  1, 4.0, 9.0, 9.0, 0.5, 9.5, 38, 70, 5, 6, "20-22"),
    ]
    for d in demos:
        sid = add_student(d[0], d[1], d[2])
        rec = {
            "sleep_duration": d[3], "deep_sleep_percentage": d[4],
            "sleep_timing": d[5], "sleep_quality": d[6],
            "study_hours": d[7], "screen_time": d[8],
            "physical_activity": d[9], "stress_level": d[10],
            "present_days": d[11], "total_days": d[12],
            "late_arrivals": d[13], "missed_first_hour": d[14],
            "age_group": d[15],
        }
        add_sleep_record(sid, rec)
        from backend.analysis import BehavioralData, analyse_student
        bdata = BehavioralData(d[3],d[4],d[5],d[6],d[7],d[8],d[9],d[10])
        result = analyse_student(bdata)
        save_prediction(sid, {
            "predicted_attendance": result.predicted_attendance,
            "attendance_risk_level": result.attendance_risk.risk_level,
            "attendance_risk_score": result.attendance_risk.probability_score,
            "fatigue_risk_level": result.fatigue_risk.risk_level,
            "fatigue_recommendation": result.fatigue_risk.recommendation,
            "sleep_score": result.sleep_metrics.sleep_score,
        })

def add_student(name, age, email):
    with get_connection() as conn:
        try:
            cur = conn.execute("INSERT INTO students (name,age,email) VALUES(?,?,?)", (name,age,email))
            return cur.lastrowid
        except sqlite3.IntegrityError:
            return conn.execute("SELECT id FROM students WHERE email=?", (email,)).fetchone()["id"]

def get_student_by_email(email) -> Optional[dict]:
    with get_connection() as conn:
        r = conn.execute("SELECT * FROM students WHERE email=?", (email,)).fetchone()
        return dict(r) if r else None

def get_all_students():
    with get_connection() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM students ORDER BY name").fetchall()]

def add_sleep_record(student_id, data):
    with get_connection() as conn:
        cur = conn.execute("""
            INSERT INTO sleep_records
            (student_id,sleep_duration,deep_sleep_percentage,sleep_timing,sleep_quality,
             study_hours,screen_time,physical_activity,stress_level,
             present_days,total_days,late_arrivals,missed_first_hour,age_group)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            student_id,
            data.get("sleep_duration",7), data.get("deep_sleep_percentage",18),
            data.get("sleep_timing",0),   data.get("sleep_quality",7),
            data.get("study_hours",4),    data.get("screen_time",4),
            data.get("physical_activity",3), data.get("stress_level",5),
            data.get("present_days",50),  data.get("total_days",60),
            data.get("late_arrivals",0),  data.get("missed_first_hour",0),
            data.get("age_group","20-22"),
        ))
        return cur.lastrowid

def get_student_records(student_id):
    with get_connection() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM sleep_records WHERE student_id=? ORDER BY record_date DESC", (student_id,)
        ).fetchall()]

def save_prediction(student_id, pred):
    with get_connection() as conn:
        cur = conn.execute("""
            INSERT INTO predictions
            (student_id,predicted_attendance,attendance_risk_level,attendance_risk_score,
             fatigue_risk_level,fatigue_recommendation,sleep_score)
            VALUES(?,?,?,?,?,?,?)
        """, (
            student_id,
            pred["predicted_attendance"], pred["attendance_risk_level"],
            pred["attendance_risk_score"], pred["fatigue_risk_level"],
            pred["fatigue_recommendation"], pred["sleep_score"],
        ))
        return cur.lastrowid

def get_latest_prediction(student_id) -> Optional[dict]:
    with get_connection() as conn:
        r = conn.execute(
            "SELECT * FROM predictions WHERE student_id=? ORDER BY created_at DESC LIMIT 1",
            (student_id,)
        ).fetchone()
        return dict(r) if r else None

def get_all_records():
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT s.name, s.age, s.email, sr.*
            FROM sleep_records sr JOIN students s ON s.id=sr.student_id
            ORDER BY sr.record_date DESC
        """).fetchall()
        return [dict(r) for r in rows]
