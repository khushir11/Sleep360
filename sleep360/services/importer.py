"""CSV import pipeline for sleep data (manual spreadsheets or wearable exports).

Stages: **extract** (decode, sniff delimiter) -> **normalise** (header aliases,
datetime parsing, unit scaling) -> **validate** (the same Pydantic schema the API
uses) -> **deduplicate** (one night per wake date; last row wins) -> **load**
(upsert, optionally overwriting manual entries) -> **recompute** assessments for
affected dates. Every rejected row is reported with its line number and reason,
and the whole load is one transaction.

Supported columns (case/spacing-insensitive, common aliases accepted):
  bedtime | sleep_start | start | start_time | in_bed            (required)
  wake_time | sleep_end | end | end_time | wake | woke_up        (required)
  quality | sleep_quality | sleep_score | rating                (1-10, or 0-100 scaled down)
  stress, daytime_sleepiness, screen_minutes_before_bed, caffeine_after_2pm,
  exercise_minutes, notes                                       (optional)
If only times (no dates) are given, a ``date`` column (wake date) is required.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from pydantic import ValidationError
from sqlalchemy import select

from ..extensions import db
from ..models import LogSource, SleepLog, User
from ..schemas import SleepLogIn
from .assessments import reassess_range

ALIASES = {
    "bedtime": ["bedtime", "sleep_start", "start", "start_time", "in_bed", "bed_time", "sleep_start_time"],
    "wake_time": ["wake_time", "sleep_end", "end", "end_time", "wake", "woke_up", "wakeup", "wake_up", "sleep_end_time"],
    "date": ["date", "wake_date", "day"],
    "quality": ["quality", "sleep_quality", "sleep_score", "rating", "score"],
    "stress": ["stress", "stress_level"],
    "daytime_sleepiness": ["daytime_sleepiness", "sleepiness", "fatigue", "tiredness"],
    "screen_minutes_before_bed": ["screen_minutes_before_bed", "screen_minutes", "screen_time", "screen"],
    "caffeine_after_2pm": ["caffeine_after_2pm", "caffeine", "late_caffeine"],
    "exercise_minutes": ["exercise_minutes", "exercise", "activity_minutes", "active_minutes"],
    "notes": ["notes", "note", "comment"],
}
DT_FORMATS = [
    "%Y-%m-%d %H:%M",
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%d-%m-%Y %H:%M",
    "%m/%d/%Y %H:%M",
    "%Y/%m/%d %H:%M",
]
TIME_FORMATS = ["%H:%M", "%H:%M:%S", "%I:%M %p", "%I:%M%p"]
DATE_FORMATS = ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y", "%Y/%m/%d"]
MAX_ROWS = 2000
TRUE = {"1", "true", "yes", "y"}
FALSE = {"0", "false", "no", "n", ""}


@dataclass
class ImportReport:
    rows: int = 0
    created: int = 0
    updated: int = 0
    skipped_existing: int = 0
    duplicates_in_file: int = 0
    errors: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {**self.__dict__, "error_count": len(self.errors), "errors": self.errors[:50]}


def _norm(h: str) -> str:
    return h.strip().lower().replace(" ", "_").replace("-", "_")


def _map_headers(headers: list[str]) -> dict[str, str]:
    normed = {_norm(h): h for h in headers if h}
    out = {}
    for canon, aliases in ALIASES.items():
        for a in aliases:
            if a in normed:
                out[canon] = normed[a]
                break
    return out


def _parse(value: str, formats: list[str]):
    v = value.strip()
    if not v:
        return None
    try:
        return datetime.fromisoformat(v.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        pass
    for f in formats:
        try:
            return datetime.strptime(v, f)
        except ValueError:
            continue
    raise ValueError(f"Unrecognised date/time '{v}'")


def _resolve_times(raw: dict, cols: dict) -> tuple[datetime, datetime]:
    bed_s, wake_s = raw[cols["bedtime"]], raw[cols["wake_time"]]
    try:
        bed, wake = _parse(bed_s, DT_FORMATS), _parse(wake_s, DT_FORMATS)
        if bed and wake and (bed.year > 1900 and wake.year > 1900):
            return bed, wake
    except ValueError:
        pass
    # time-only columns: need a wake date
    if "date" not in cols:
        raise ValueError("Times without dates need a 'date' (wake date) column")
    d = _parse(raw[cols["date"]], DATE_FORMATS)
    if d is None:
        raise ValueError("Missing date")
    bt = _parse(bed_s, TIME_FORMATS)
    wt = _parse(wake_s, TIME_FORMATS)
    if bt is None or wt is None:
        raise ValueError("Missing bedtime or wake time")
    wake = datetime.combine(d.date(), wt.time())
    bed = datetime.combine(d.date(), bt.time())
    if bed >= wake:
        bed -= timedelta(days=1)
    return bed, wake


def _num(v: str | None, scale_100: bool = False):
    if v is None or not str(v).strip():
        return None
    x = float(v)
    if scale_100 and x > 10:
        x = x / 10  # 0-100 score -> 1-10
    return max(1, round(x)) if scale_100 else round(x)


def _bool(v: str | None):
    if v is None:
        return None
    s = str(v).strip().lower()
    if s in TRUE:
        return True
    if s in FALSE:
        return None if s == "" else False
    raise ValueError(f"Expected yes/no for caffeine, got '{v}'")


def import_csv(user: User, content: bytes, overwrite: bool = False) -> ImportReport:
    rep = ImportReport()
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")
    try:
        dialect = csv.Sniffer().sniff(text[:2048], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    cols = _map_headers(reader.fieldnames or [])
    if "bedtime" not in cols or "wake_time" not in cols:
        rep.errors.append({"line": 1, "error": "CSV needs bedtime and wake time columns (see the import guide)."})
        return rep

    parsed: dict[date, SleepLogIn] = {}
    for i, raw in enumerate(reader, start=2):
        if rep.rows >= MAX_ROWS:
            rep.errors.append({"line": i, "error": f"Row limit of {MAX_ROWS} reached; remaining rows ignored."})
            break
        rep.rows += 1
        try:
            bed, wake = _resolve_times(raw, cols)
            g = lambda k, raw=raw: raw.get(cols[k]) if k in cols else None  # noqa: E731
            quality = _num(g("quality"), scale_100=True)
            payload = SleepLogIn(
                bedtime=bed,
                wake_time=wake,
                quality=quality if quality is not None else 6,
                stress=_num(g("stress")),
                daytime_sleepiness=_num(g("daytime_sleepiness")),
                screen_minutes_before_bed=_num(g("screen_minutes_before_bed")),
                caffeine_after_2pm=_bool(g("caffeine_after_2pm")),
                exercise_minutes=_num(g("exercise_minutes")),
                notes=(g("notes") or None),
            )
        except ValidationError as e:
            rep.errors.append({"line": i, "error": "; ".join(err["msg"].replace("Value error, ", "") for err in e.errors())})
            continue
        except (ValueError, TypeError) as e:
            rep.errors.append({"line": i, "error": str(e)})
            continue
        if payload.date in parsed:
            rep.duplicates_in_file += 1
        parsed[payload.date] = payload

    if not parsed:
        return rep

    existing = {
        x.date: x
        for x in db.session.scalars(select(SleepLog).where(SleepLog.user_id == user.id, SleepLog.date.in_(list(parsed))))
    }
    for d, p in parsed.items():
        fields = p.model_dump()
        row = existing.get(d)
        if row is not None:
            if not overwrite:
                rep.skipped_existing += 1
                continue
            for k, v in fields.items():
                setattr(row, k, v)
            row.source = LogSource.csv
            rep.updated += 1
        else:
            db.session.add(SleepLog(user_id=user.id, date=d, source=LogSource.csv, **fields))
            rep.created += 1
    db.session.flush()
    if rep.created or rep.updated:
        reassess_range(user, min(parsed), max(parsed) + timedelta(days=7))
    else:
        db.session.commit()
    return rep
