"""Synthetic training data generator.

IMPORTANT -- READ BEFORE QUOTING ANY RESULT
-------------------------------------------
This module *simulates* students. No real student data is involved. The label
(next-day fatigue, defined as self-reported daytime sleepiness >= 7/10) is produced
by a hand-written generative model whose coefficients are ASSUMPTIONS chosen so that
the *direction* of each effect matches well-established findings (e.g. short and
irregular sleep increase daytime sleepiness), while the *magnitudes* are invented.

Consequently, a model trained on this data can only rediscover these assumptions.
Its metrics measure how well the pipeline recovers a known signal under noise --
they are NOT evidence about real students. The pipeline exists so that, once the app
has collected enough real, consented, labelled logs, the same code can be retrained
on them (``flask ml train --source db``).

Design choices that make the simulation non-trivial:
* students have persistent latent traits (chronotype, regularity, sleep need,
  stress baseline, habits) -> repeated measures, so CV must be grouped by student;
* the sleep effect is a hinge (non-linear) and there is a stress x short-sleep
  interaction, giving tree models something a linear model cannot fully capture;
* a per-student random intercept and label noise cap achievable accuracy.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import numpy as np

from .features import FEATURES, build_features

# Generative-model coefficients (log-odds scale). ASSUMED, see module docstring.
GENERATIVE_COEFFICIENTS = {
    "intercept": -2.2,
    "short_sleep_hinge_per_hour_below_7": 0.85,
    "sleep_debt_7d_per_hour": 0.12,
    "bedtime_sd_per_10min": 0.10,
    "late_bedtime_per_hour_after_midnight": 0.18,
    "stress_per_point_above_5": 0.22,
    "stress_x_short_sleep": 0.10,
    "screen_per_30min": 0.08,
    "caffeine_late": 0.30,
    "exercise_per_30min": -0.12,
    "quality_per_point_above_6": -0.18,
    "student_random_effect_sd": 0.6,
}


@dataclass
class SimConfig:
    n_students: int = 400
    days: int = 60
    goal_hours: float = 8.0
    seed: int = 42


def _logit_to_p(z: float) -> float:
    return 1 / (1 + math.exp(-z))


def _fatigue_logit(f: dict, u: float) -> float:
    c = GENERATIVE_COEFFICIENTS
    short = max(0.0, 7.0 - f["sleep_hours"])
    late_after_midnight = max(0.0, f["bedtime_rel_hours"] - 6.0)
    return (
        c["intercept"]
        + c["short_sleep_hinge_per_hour_below_7"] * short
        + c["sleep_debt_7d_per_hour"] * f["sleep_debt_7d"]
        + c["bedtime_sd_per_10min"] * f["bedtime_sd_7d"] / 10
        + c["late_bedtime_per_hour_after_midnight"] * late_after_midnight
        + c["stress_per_point_above_5"] * (f["stress"] - 5)
        + c["stress_x_short_sleep"] * max(0.0, f["stress"] - 5) * short
        + c["screen_per_30min"] * f["screen_minutes"] / 30
        + c["caffeine_late"] * f["caffeine_late"]
        + c["exercise_per_30min"] * f["exercise_minutes"] / 30
        + c["quality_per_point_above_6"] * (f["quality"] - 6)
        + u
    )


def simulate(cfg: SimConfig = SimConfig()) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (X, y, groups) where groups is the simulated student id for each row."""
    rng = np.random.default_rng(cfg.seed)
    X, y, groups = [], [], []
    start = date(2025, 1, 6)
    for sid in range(cfg.n_students):
        chrono = rng.normal(5.0, 1.0)  # habitual bedtime, hours after 18:00 (5.0 = 23:00)
        irregular = abs(rng.normal(0.6, 0.35))  # night-to-night bedtime SD (hours)
        need = rng.normal(7.3, 0.5)
        stress_base = float(np.clip(rng.normal(5, 1.6), 1, 10))
        screen_base = max(0.0, rng.normal(50, 30))
        caffeine_p = float(np.clip(rng.beta(2, 5), 0, 1))
        exercise_base = max(0.0, rng.normal(25, 18))
        u = rng.normal(0, GENERATIVE_COEFFICIENTS["student_random_effect_sd"])

        logs = []
        for d in range(cfg.days):
            day = start + timedelta(days=d)
            weekend = day.weekday() >= 5
            exam_crunch = (d % 30) in range(22, 28)
            stress = float(np.clip(round(stress_base + rng.normal(0, 1.2) + (1.5 if exam_crunch else 0)), 1, 10))
            bed_rel = chrono + rng.normal(0, irregular) + (0.8 if weekend else 0) + (0.5 if exam_crunch else 0)
            bed_rel += 0.04 * (stress - 5)
            bed_rel = float(np.clip(bed_rel, 2.0, 11.0))
            wake_rel = (13.0 + rng.normal(0, 0.35)) if not weekend else (bed_rel + need + rng.normal(0.3, 0.6))
            wake_rel = max(wake_rel, bed_rel + 3.0)
            screen = max(0, int(rng.normal(screen_base, 20)))
            caffeine = bool(rng.random() < caffeine_p + (0.15 if exam_crunch else 0))
            exercise = max(0, int(rng.normal(exercise_base, 15))) if rng.random() > 0.3 else 0
            dur = wake_rel - bed_rel
            q = 6.5 + 0.6 * (dur - 7) - 0.25 * (stress - 5) - 0.006 * screen - 0.5 * caffeine + 0.01 * exercise
            quality = int(np.clip(round(q + rng.normal(0, 1.2)), 1, 10))
            anchor = datetime.combine(day - timedelta(days=1), datetime.min.time()) + timedelta(hours=18)
            logs.append(
                SimpleNamespace(
                    date=day,
                    bedtime=anchor + timedelta(hours=bed_rel),
                    wake_time=anchor + timedelta(hours=wake_rel),
                    quality=quality,
                    stress=int(stress),
                    screen_minutes_before_bed=screen,
                    caffeine_after_2pm=caffeine,
                    exercise_minutes=exercise,
                )
            )
        for d in range(7, cfg.days):  # skip warm-up days without a full window
            f = build_features(logs, logs[d].date, cfg.goal_hours)
            p = _logit_to_p(_fatigue_logit(f, u))
            X.append([f[k] for k in FEATURES])
            y.append(int(rng.random() < p))
            groups.append(sid)
    return np.asarray(X, dtype=float), np.asarray(y, dtype=int), np.asarray(groups)
