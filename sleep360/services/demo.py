"""Demo accounts.

"Try the demo" creates a *fresh, isolated* demo user per visitor (flagged
``is_demo``) seeded with realistic generated data. Visitors never share or see each
other's data, and ``flask demo cleanup`` removes stale demo accounts.
"""

from __future__ import annotations

import random
import secrets
from datetime import datetime, time, timedelta

from sqlalchemy import select

from ..extensions import db
from ..models import (
    AttendanceRecord,
    AttendanceStatus,
    LogSource,
    Semester,
    SleepLog,
    StudySession,
    Subject,
    Task,
    TaskKind,
    User,
    utcnow,
)
from .assessments import reassess_range
from .queries import user_today

SUBJECTS = [
    ("Data Structures", "CS201", 4, "#5b5bd6", 0.90),
    ("Database Systems", "CS204", 3, "#0e9f6e", 0.82),
    ("Operating Systems", "CS206", 3, "#d97706", 0.74),
    ("Discrete Mathematics", "MA202", 4, "#db2777", 0.70),
    ("Software Lab", "CS281", 2, "#0891b2", 0.95),
]


def create_demo_user(name: str = "Demo Student", email: str | None = None, days: int = 45, seed: int | None = None) -> User:
    rng = random.Random(seed)
    email = email or f"demo-{secrets.token_hex(5)}@demo.sleep360.local"
    u = User(
        name=name,
        email=email,
        is_demo=True,
        sleep_goal_hours=8.0,
        target_wake_time=time(7, 0),
        attendance_target=75.0,
        study_goal_hours_week=18.0,
    )
    u.set_password(secrets.token_urlsafe(24))  # nobody knows it; demo logins are session-based
    db.session.add(u)
    db.session.flush()

    today = user_today(u)
    # ---- sleep logs: a student who drifts late during an exam crunch, then recovers
    for i in range(days, 0, -1):
        d = today - timedelta(days=i - 1)
        crunch = 12 <= i <= 20
        weekend = d.weekday() >= 5
        bed_h = 23.4 + rng.gauss(0, 0.55) + (1.2 if crunch else 0) + (0.9 if weekend else 0)
        wake_h = 7.0 + rng.gauss(0, 0.25) + (1.6 if weekend else 0) - (0.3 if crunch else 0)
        bed = datetime.combine(d - timedelta(days=1), time(0)) + timedelta(hours=bed_h)
        wake = datetime.combine(d, time(0)) + timedelta(hours=wake_h)
        dur = (wake - bed).total_seconds() / 3600
        stress = max(1, min(10, round(5 + rng.gauss(0, 1.2) + (2.5 if crunch else 0))))
        screen = max(0, int(rng.gauss(55 if crunch else 35, 18)))
        caffeine = rng.random() < (0.6 if crunch else 0.2)
        quality = max(1, min(10, round(6 + 0.8 * (dur - 7) - 0.3 * (stress - 5) - (0.7 if caffeine else 0) + rng.gauss(0, 1))))
        sleepiness = max(1, min(10, round(4 + 0.9 * max(0, 7 - dur) + 0.3 * (stress - 5) + rng.gauss(0, 1.2))))
        db.session.add(
            SleepLog(
                user_id=u.id,
                date=d,
                bedtime=bed.replace(second=0, microsecond=0),
                wake_time=wake.replace(second=0, microsecond=0),
                quality=quality,
                stress=stress,
                daytime_sleepiness=sleepiness,
                screen_minutes_before_bed=screen,
                caffeine_after_2pm=caffeine,
                exercise_minutes=max(0, int(rng.gauss(25, 18))) if rng.random() > 0.25 else 0,
                source=LogSource.demo,
            )
        )

    # ---- semester + attendance
    sem = Semester(
        user_id=u.id,
        name="Semester 4",
        start_date=today - timedelta(days=70),
        end_date=today + timedelta(days=50),
        is_active=True,
    )
    db.session.add(sem)
    db.session.flush()
    subjects = []
    for name, code, per_week, color, rate in SUBJECTS:
        s = Subject(
            user_id=u.id,
            semester_id=sem.id,
            name=name,
            code=code,
            classes_per_week=per_week,
            color=color,
            initial_conducted=int(per_week * 4),
            initial_attended=int(per_week * 4 * min(1, rate + 0.05)),
            target_override=80.0 if "Lab" in name else None,
        )
        db.session.add(s)
        subjects.append((s, per_week, rate))
    db.session.flush()
    weekdays_for = {4: [0, 1, 3, 4], 3: [0, 2, 4], 2: [1, 3]}
    for s, per_week, rate in subjects:
        for i in range(42, -1, -1):
            d = today - timedelta(days=i)
            if d.weekday() not in weekdays_for[per_week]:
                continue
            crunch = 12 <= i + 1 <= 20
            r = rng.random()
            if r < 0.03:
                st = AttendanceStatus.cancelled
            elif r < rate - (0.15 if crunch else 0):
                st = AttendanceStatus.present
            else:
                st = AttendanceStatus.absent
            db.session.add(AttendanceRecord(subject_id=s.id, date=d, status=st))

    # ---- tasks + study sessions
    now = datetime.combine(today, time(9, 0))
    sub = {s.code: s for s, _, _ in subjects}
    tasks = [
        Task(
            user_id=u.id,
            subject_id=sub["CS206"].id,
            title="OS mid-term exam",
            kind=TaskKind.exam,
            due_at=now + timedelta(days=4, hours=1),
            estimated_minutes=480,
            priority=1,
        ),
        Task(
            user_id=u.id,
            subject_id=sub["CS204"].id,
            title="DBMS assignment 3: normalisation",
            kind=TaskKind.assignment,
            due_at=now + timedelta(days=2, hours=14),
            estimated_minutes=150,
            priority=1,
        ),
        Task(
            user_id=u.id,
            subject_id=sub["MA202"].id,
            title="Discrete maths problem set 6",
            kind=TaskKind.assignment,
            due_at=now + timedelta(days=6, hours=8),
            estimated_minutes=120,
            priority=2,
        ),
        Task(
            user_id=u.id,
            subject_id=sub["CS281"].id,
            title="Lab record write-up",
            kind=TaskKind.assignment,
            due_at=now + timedelta(hours=30),
            estimated_minutes=60,
            priority=2,
        ),
        Task(
            user_id=u.id,
            subject_id=sub["CS201"].id,
            title="Revise graph algorithms",
            kind=TaskKind.study,
            due_at=None,
            estimated_minutes=90,
            priority=3,
        ),
    ]
    for i in range(10):
        tasks.append(
            Task(
                user_id=u.id,
                title=f"Completed task {i + 1}",
                kind=TaskKind.assignment,
                done=True,
                due_at=now - timedelta(days=30 - 2 * i),
                completed_at=now - timedelta(days=30 - 2 * i),
                estimated_minutes=60,
                priority=2,
                subject_id=subjects[i % 5][0].id,
            )
        )
    db.session.add_all(tasks)
    db.session.flush()
    for i in range(13, -1, -1):
        d = today - timedelta(days=i)
        for _ in range(rng.choice([0, 1, 2, 2, 3])):
            s, _, _ = rng.choice(subjects)
            db.session.add(
                StudySession(
                    user_id=u.id,
                    subject_id=s.id,
                    started_at=datetime.combine(d, time(rng.choice([16, 17, 18, 19, 20]), rng.choice([0, 30]))),
                    duration_minutes=rng.choice([25, 40, 50, 50, 60, 90]),
                    focus=rng.randint(2, 5),
                    task_id=tasks[0].id if s.code == "CS206" and rng.random() < 0.5 else None,
                )
            )
    db.session.commit()
    reassess_range(u, today - timedelta(days=days - 1), today)
    return u


def cleanup(older_than_days: int = 2) -> int:
    cutoff = utcnow() - timedelta(days=older_than_days)
    ids = list(db.session.scalars(select(User.id).where(User.is_demo.is_(True), User.created_at < cutoff)))
    if ids:
        for u in db.session.scalars(select(User).where(User.id.in_(ids))):
            db.session.delete(u)  # ORM cascade handles children on every backend
        db.session.commit()
    return len(ids)
