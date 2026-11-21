"""Request validation schemas (Pydantic v2).

Every write endpoint validates its body against one of these. Validation errors are
turned into a uniform 422 response by ``api.errors``.
"""

from __future__ import annotations

import re
from datetime import date, datetime, time
from typing import Literal
from zoneinfo import available_timezones

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# ── auth / account ───────────────────────────────────────────────────────
class RegisterIn(Strict):
    name: str = Field(min_length=1, max_length=80)
    email: str = Field(max_length=254)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.lower()
        if not EMAIL_RE.match(v):
            raise ValueError("Enter a valid email address")
        return v

    @field_validator("password")
    @classmethod
    def _password(cls, v: str) -> str:
        if not (re.search(r"[A-Za-z]", v) and re.search(r"\d", v)):
            raise ValueError("Password must contain at least one letter and one number")
        return v


class LoginIn(Strict):
    email: str = Field(max_length=254)
    password: str = Field(max_length=128)
    remember: bool = False

    @field_validator("email")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.lower()


class SettingsIn(Strict):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    timezone: str | None = None
    sleep_goal_hours: float | None = Field(default=None, ge=5, le=11)
    target_wake_time: time | None = None
    attendance_target: float | None = Field(default=None, ge=50, le=100)
    study_goal_hours_week: float | None = Field(default=None, ge=0, le=80)
    ai_assistant_enabled: bool | None = None

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v: str | None) -> str | None:
        if v is not None and v not in available_timezones():
            raise ValueError("Unknown timezone")
        return v


class PasswordChangeIn(Strict):
    current_password: str = Field(max_length=128)
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def _password(cls, v: str) -> str:
        if not (re.search(r"[A-Za-z]", v) and re.search(r"\d", v)):
            raise ValueError("Password must contain at least one letter and one number")
        return v


class DeleteAccountIn(Strict):
    password: str = Field(max_length=128)


# ── sleep ────────────────────────────────────────────────────────────────
class SleepLogIn(Strict):
    bedtime: datetime
    wake_time: datetime
    quality: int = Field(ge=1, le=10)
    daytime_sleepiness: int | None = Field(default=None, ge=1, le=10)
    stress: int | None = Field(default=None, ge=1, le=10)
    screen_minutes_before_bed: int | None = Field(default=None, ge=0, le=600)
    caffeine_after_2pm: bool | None = None
    exercise_minutes: int | None = Field(default=None, ge=0, le=600)
    notes: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _times(self) -> SleepLogIn:
        # Accept tz-aware input but store naive local time
        self.bedtime = self.bedtime.replace(tzinfo=None, second=0, microsecond=0)
        self.wake_time = self.wake_time.replace(tzinfo=None, second=0, microsecond=0)
        hours = (self.wake_time - self.bedtime).total_seconds() / 3600
        if hours <= 0:
            raise ValueError("Wake time must be after bedtime")
        if hours > 16:
            raise ValueError("Sleep periods longer than 16 hours are not accepted")
        return self

    @property
    def date(self) -> date:
        return self.wake_time.date()


# ── attendance ───────────────────────────────────────────────────────────
class SemesterIn(Strict):
    name: str = Field(min_length=1, max_length=80)
    start_date: date
    end_date: date
    is_active: bool = True

    @model_validator(mode="after")
    def _range(self) -> SemesterIn:
        if self.end_date <= self.start_date:
            raise ValueError("Semester end date must be after its start date")
        return self


class SubjectIn(Strict):
    semester_id: int
    name: str = Field(min_length=1, max_length=100)
    code: str | None = Field(default=None, max_length=20)
    classes_per_week: float = Field(default=3, ge=0, le=30)
    target_override: float | None = Field(default=None, ge=50, le=100)
    initial_conducted: int = Field(default=0, ge=0, le=2000)
    initial_attended: int = Field(default=0, ge=0, le=2000)
    color: str = Field(default="#5b5bd6", pattern=r"^#[0-9a-fA-F]{6}$")

    @model_validator(mode="after")
    def _counts(self) -> SubjectIn:
        if self.initial_attended > self.initial_conducted:
            raise ValueError("Attended classes cannot exceed conducted classes")
        return self


class SubjectUpdateIn(Strict):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    code: str | None = Field(default=None, max_length=20)
    classes_per_week: float | None = Field(default=None, ge=0, le=30)
    target_override: float | None = Field(default=None, ge=50, le=100)
    initial_conducted: int | None = Field(default=None, ge=0, le=2000)
    initial_attended: int | None = Field(default=None, ge=0, le=2000)
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")


class AttendanceMarkIn(Strict):
    subject_id: int
    date: date
    status: Literal["present", "absent", "cancelled"]
    period: int = Field(default=1, ge=1, le=8)


# ── planner ──────────────────────────────────────────────────────────────
class TaskIn(Strict):
    title: str = Field(min_length=1, max_length=160)
    kind: Literal["assignment", "exam", "study", "other"] = "assignment"
    subject_id: int | None = None
    due_at: datetime | None = None
    estimated_minutes: int = Field(default=60, ge=5, le=6000)
    priority: int = Field(default=2, ge=1, le=3)


class TaskUpdateIn(Strict):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    kind: Literal["assignment", "exam", "study", "other"] | None = None
    subject_id: int | None = None
    due_at: datetime | None = None
    estimated_minutes: int | None = Field(default=None, ge=5, le=6000)
    priority: int | None = Field(default=None, ge=1, le=3)
    done: bool | None = None


class StudySessionIn(Strict):
    started_at: datetime
    duration_minutes: int = Field(ge=1, le=600)
    subject_id: int | None = None
    task_id: int | None = None
    focus: int | None = Field(default=None, ge=1, le=5)


# ── assistant ────────────────────────────────────────────────────────────
class ChatIn(Strict):
    message: str = Field(min_length=1, max_length=2000)
