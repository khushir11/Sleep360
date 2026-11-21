"""Database models.

Design notes
------------
* Every user-owned table carries ``user_id`` (directly or via its parent) and every
  query in the service layer filters on it -- this is the core privacy guarantee.
* ``SleepLog`` is one row per user per *wake date* (unique constraint) so re-logging
  a night is an upsert, not a duplicate.
* Attendance is stored per class (``AttendanceRecord``) plus an optional opening
  balance on ``Subject`` (``initial_conducted`` / ``initial_attended``) so a student
  who starts using the app mid-semester can enter their totals once.
* Derived values (sleep duration, attendance %) are computed, never stored twice,
  except ``RiskAssessment`` which snapshots model output so changes over time can be
  explained.
"""

from __future__ import annotations

import enum
from datetime import UTC, date, datetime, time

from flask_login import UserMixin
from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


# ─────────────────────────────────────────────────────────────── users ──
class User(UserMixin, TimestampMixin, db.Model):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Goals & institutional settings
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Kolkata", nullable=False)
    sleep_goal_hours: Mapped[float] = mapped_column(Float, default=8.0, nullable=False)
    target_wake_time: Mapped[time] = mapped_column(Time, default=time(7, 0), nullable=False)
    attendance_target: Mapped[float] = mapped_column(Float, default=75.0, nullable=False)
    study_goal_hours_week: Mapped[float] = mapped_column(Float, default=20.0, nullable=False)
    ai_assistant_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    sleep_logs: Mapped[list[SleepLog]] = relationship(back_populates="user", cascade="all, delete-orphan")
    semesters: Mapped[list[Semester]] = relationship(back_populates="user", cascade="all, delete-orphan")
    subjects: Mapped[list[Subject]] = relationship(back_populates="user", cascade="all, delete-orphan")
    tasks: Mapped[list[Task]] = relationship(back_populates="user", cascade="all, delete-orphan")
    study_sessions: Mapped[list[StudySession]] = relationship(back_populates="user", cascade="all, delete-orphan")
    assessments: Mapped[list[RiskAssessment]] = relationship(back_populates="user", cascade="all, delete-orphan")
    chat_messages: Mapped[list[ChatMessage]] = relationship(back_populates="user", cascade="all, delete-orphan")
    notifications: Mapped[list[Notification]] = relationship(back_populates="user", cascade="all, delete-orphan")
    achievements: Mapped[list[Achievement]] = relationship(back_populates="user", cascade="all, delete-orphan")

    def set_password(self, raw: str) -> None:
        self.password_hash = generate_password_hash(raw)  # scrypt by default in Werkzeug 3

    def check_password(self, raw: str) -> bool:
        return check_password_hash(self.password_hash, raw)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "is_demo": self.is_demo,
            "timezone": self.timezone,
            "sleep_goal_hours": self.sleep_goal_hours,
            "target_wake_time": self.target_wake_time.strftime("%H:%M"),
            "attendance_target": self.attendance_target,
            "study_goal_hours_week": self.study_goal_hours_week,
            "ai_assistant_enabled": self.ai_assistant_enabled,
            "created_at": self.created_at.isoformat(),
        }


# ─────────────────────────────────────────────────────────────── sleep ──
class LogSource(str, enum.Enum):
    manual = "manual"
    csv = "csv"
    demo = "demo"


class SleepLog(TimestampMixin, db.Model):
    __tablename__ = "sleep_logs"
    __table_args__ = (
        UniqueConstraint("user_id", "date", name="uq_sleep_user_date"),
        Index("ix_sleep_user_date", "user_id", "date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)  # the morning you woke up
    bedtime: Mapped[datetime] = mapped_column(DateTime, nullable=False)  # local, naive
    wake_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    quality: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-10 self-rated
    daytime_sleepiness: Mapped[int | None] = mapped_column(Integer)  # 1-10, label for ML
    stress: Mapped[int | None] = mapped_column(Integer)  # 1-10
    screen_minutes_before_bed: Mapped[int | None] = mapped_column(Integer)
    caffeine_after_2pm: Mapped[bool | None] = mapped_column(Boolean)
    exercise_minutes: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(String(500))
    source: Mapped[LogSource] = mapped_column(Enum(LogSource), default=LogSource.manual, nullable=False)

    user: Mapped[User] = relationship(back_populates="sleep_logs")

    @property
    def duration_hours(self) -> float:
        return round((self.wake_time - self.bedtime).total_seconds() / 3600, 2)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "date": self.date.isoformat(),
            "bedtime": self.bedtime.isoformat(timespec="minutes"),
            "wake_time": self.wake_time.isoformat(timespec="minutes"),
            "duration_hours": self.duration_hours,
            "quality": self.quality,
            "daytime_sleepiness": self.daytime_sleepiness,
            "stress": self.stress,
            "screen_minutes_before_bed": self.screen_minutes_before_bed,
            "caffeine_after_2pm": self.caffeine_after_2pm,
            "exercise_minutes": self.exercise_minutes,
            "notes": self.notes,
            "source": self.source.value,
        }


# ────────────────────────────────────────────────────────── attendance ──
class Semester(TimestampMixin, db.Model):
    __tablename__ = "semesters"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    user: Mapped[User] = relationship(back_populates="semesters")
    subjects: Mapped[list[Subject]] = relationship(back_populates="semester", cascade="all, delete-orphan")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "is_active": self.is_active,
        }


class Subject(TimestampMixin, db.Model):
    __tablename__ = "subjects"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    semester_id: Mapped[int] = mapped_column(ForeignKey("semesters.id", ondelete="CASCADE"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str | None] = mapped_column(String(20))
    classes_per_week: Mapped[float] = mapped_column(Float, default=3, nullable=False)
    target_override: Mapped[float | None] = mapped_column(Float)  # e.g. labs need 80%
    initial_conducted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    initial_attended: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    color: Mapped[str] = mapped_column(String(9), default="#5b5bd6", nullable=False)

    user: Mapped[User] = relationship(back_populates="subjects")
    semester: Mapped[Semester] = relationship(back_populates="subjects")
    records: Mapped[list[AttendanceRecord]] = relationship(back_populates="subject", cascade="all, delete-orphan")


class AttendanceStatus(str, enum.Enum):
    present = "present"
    absent = "absent"
    cancelled = "cancelled"  # does not count as conducted


class AttendanceRecord(TimestampMixin, db.Model):
    __tablename__ = "attendance_records"
    __table_args__ = (UniqueConstraint("subject_id", "date", "period", name="uq_attendance_slot"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"), index=True, nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    period: Mapped[int] = mapped_column(Integer, default=1, nullable=False)  # 2nd class same day = 2
    status: Mapped[AttendanceStatus] = mapped_column(Enum(AttendanceStatus), nullable=False)

    subject: Mapped[Subject] = relationship(back_populates="records")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "subject_id": self.subject_id,
            "date": self.date.isoformat(),
            "period": self.period,
            "status": self.status.value,
        }


# ───────────────────────────────────────────────────────────── planner ──
class TaskKind(str, enum.Enum):
    assignment = "assignment"
    exam = "exam"
    study = "study"
    other = "other"


class Task(TimestampMixin, db.Model):
    __tablename__ = "tasks"
    __table_args__ = (Index("ix_tasks_user_status_due", "user_id", "done", "due_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    subject_id: Mapped[int | None] = mapped_column(ForeignKey("subjects.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    kind: Mapped[TaskKind] = mapped_column(Enum(TaskKind), default=TaskKind.assignment, nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime)
    estimated_minutes: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=2, nullable=False)  # 1 high .. 3 low
    done: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)

    user: Mapped[User] = relationship(back_populates="tasks")
    subject: Mapped[Subject | None] = relationship()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "kind": self.kind.value,
            "subject_id": self.subject_id,
            "subject_name": self.subject.name if self.subject else None,
            "due_at": self.due_at.isoformat(timespec="minutes") if self.due_at else None,
            "estimated_minutes": self.estimated_minutes,
            "priority": self.priority,
            "done": self.done,
            "completed_at": self.completed_at.isoformat(timespec="minutes") if self.completed_at else None,
        }


class StudySession(TimestampMixin, db.Model):
    __tablename__ = "study_sessions"
    __table_args__ = (Index("ix_study_user_started", "user_id", "started_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    subject_id: Mapped[int | None] = mapped_column(ForeignKey("subjects.id", ondelete="SET NULL"))
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"))
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    focus: Mapped[int | None] = mapped_column(Integer)  # 1-5

    user: Mapped[User] = relationship(back_populates="study_sessions")
    subject: Mapped[Subject | None] = relationship()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "subject_id": self.subject_id,
            "subject_name": self.subject.name if self.subject else None,
            "task_id": self.task_id,
            "started_at": self.started_at.isoformat(timespec="minutes"),
            "duration_minutes": self.duration_minutes,
            "focus": self.focus,
        }


# ────────────────────────────────────────────────────── ML / insights ──
class RiskAssessment(TimestampMixin, db.Model):
    """Snapshot of model output for one user-day, used to explain changes over time."""

    __tablename__ = "risk_assessments"
    __table_args__ = (UniqueConstraint("user_id", "date", name="uq_assessment_user_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    sleep_score: Mapped[float] = mapped_column(Float, nullable=False)
    fatigue_probability: Mapped[float | None] = mapped_column(Float)
    fatigue_level: Mapped[str | None] = mapped_column(String(10))
    model_version: Mapped[str | None] = mapped_column(String(80))
    details: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    user: Mapped[User] = relationship(back_populates="assessments")


class ChatMessage(TimestampMixin, db.Model):
    __tablename__ = "chat_messages"
    __table_args__ = (Index("ix_chat_user_created", "user_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(10), nullable=False)  # user | assistant
    content: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str | None] = mapped_column(String(20))  # anthropic | fallback

    user: Mapped[User] = relationship(back_populates="chat_messages")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "role": self.role,
            "content": self.content,
            "provider": self.provider,
            "created_at": self.created_at.isoformat(timespec="seconds"),
        }


class Notification(TimestampMixin, db.Model):
    __tablename__ = "notifications"
    __table_args__ = (UniqueConstraint("user_id", "dedupe_key", name="uq_notification_dedupe"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    title: Mapped[str] = mapped_column(String(140), nullable=False)
    body: Mapped[str] = mapped_column(String(500), nullable=False)
    link: Mapped[str | None] = mapped_column(String(200))
    dedupe_key: Mapped[str] = mapped_column(String(120), nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime)

    user: Mapped[User] = relationship(back_populates="notifications")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "title": self.title,
            "body": self.body,
            "link": self.link,
            "read": self.read_at is not None,
            "created_at": self.created_at.isoformat(timespec="seconds"),
        }


class Achievement(db.Model):
    __tablename__ = "achievements"
    __table_args__ = (UniqueConstraint("user_id", "code", name="uq_achievement_user_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    earned_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    user: Mapped[User] = relationship(back_populates="achievements")
