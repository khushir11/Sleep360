"""
Sleep360 – Analysis & Prediction Engine
"""
from dataclasses import dataclass
from typing import Literal

RiskLevel = Literal["low", "moderate", "high"]

@dataclass
class BehavioralData:
    sleep_duration: float
    deep_sleep_percentage: float
    sleep_timing: int            # 0=before midnight, 1=after midnight
    sleep_quality: float         # 1-10
    study_hours: float
    screen_time: float
    physical_activity: float     # hrs/week
    stress_level: float          # 1-10

@dataclass
class SleepMetrics:
    avg_duration: float
    quality_label: str
    late_freq: int
    sleep_score: float
    deep_pct: float
    consistency_score: float

@dataclass
class AttendanceRisk:
    probability_score: float
    risk_level: RiskLevel

@dataclass
class FatigueRisk:
    risk_level: RiskLevel
    recommendation: str

@dataclass
class PredictionResult:
    predicted_attendance: float
    attendance_risk: AttendanceRisk
    fatigue_risk: FatigueRisk
    sleep_metrics: SleepMetrics
    optimal_sleep: float
    habit_impact: str


def compute_sleep_metrics(d: BehavioralData) -> SleepMetrics:
    dur, deep = d.sleep_duration, d.deep_sleep_percentage
    if dur >= 7 and deep >= 20:   quality = "Excellent"
    elif dur >= 6 and deep >= 15: quality = "Good"
    elif dur >= 5:                quality = "Fair"
    else:                         quality = "Poor"

    late_freq = 5 if d.sleep_timing == 1 else 1
    dur_score  = min((dur / 8.0) * 40, 40)
    deep_score = min((deep / 25.0) * 30, 30)
    timing_score = 30 if d.sleep_timing == 0 else 10
    sleep_score = round(dur_score + deep_score + timing_score, 1)

    # Consistency score based on quality + stress
    consistency = max(0, min(100, round(100 - (d.stress_level - 1) * 8 - (10 - d.sleep_quality) * 3, 1)))

    return SleepMetrics(
        avg_duration=dur, quality_label=quality, late_freq=late_freq,
        sleep_score=sleep_score, deep_pct=deep, consistency_score=consistency
    )


def predict_attendance(d: BehavioralData) -> float:
    s = 50.0
    s += (d.sleep_duration - 4) * 4.0
    s += d.sleep_quality * 1.5
    s += d.deep_sleep_percentage * 0.3
    s -= d.sleep_timing * 8.0
    s += d.study_hours * 2.0
    s -= d.screen_time * 1.5
    s += d.physical_activity * 0.8
    s -= (d.stress_level - 5) * 1.2
    return max(0.0, min(100.0, round(s, 2)))


def compute_attendance_risk(predicted: float) -> AttendanceRisk:
    if predicted >= 85:
        return AttendanceRisk(max(0, round(5 + (85-predicted), 1)), "low")
    elif predicted >= 75:
        return AttendanceRisk(min(100, round(20 + (85-predicted)*3, 1)), "moderate")
    else:
        return AttendanceRisk(min(100, round(60 + (75-predicted)*2, 1)), "high")


def compute_fatigue_risk(d: BehavioralData) -> FatigueRisk:
    fs = 0
    if d.sleep_duration < 6:  fs += 3
    elif d.sleep_duration < 7: fs += 1
    if d.sleep_timing == 1:   fs += 2
    if d.stress_level >= 7:   fs += 2
    if d.screen_time >= 5:    fs += 1
    if d.physical_activity < 2: fs += 1

    if fs >= 6:
        return FatigueRisk("high",
            "⚠️ Critical fatigue risk! Aim for 7–9h sleep, reduce screen time before bed, consider counseling.")
    elif fs >= 3:
        return FatigueRisk("moderate",
            "🟡 Moderate fatigue. Establish a consistent bedtime before midnight & exercise 30 min/day.")
    return FatigueRisk("low",
        "✅ Good sleep hygiene! Maintain your healthy schedule and stay consistent with exercise.")


def compute_optimal_sleep(d: BehavioralData) -> float:
    """Compute ideal sleep hours for this individual."""
    base = 8.0
    if d.stress_level >= 7:  base += 0.5
    if d.physical_activity >= 5: base += 0.5
    if d.study_hours >= 8:   base += 0.5
    return min(9.5, base)


def analyse_student(d: BehavioralData) -> PredictionResult:
    sm  = compute_sleep_metrics(d)
    att = predict_attendance(d)
    ar  = compute_attendance_risk(att)
    fr  = compute_fatigue_risk(d)
    opt = compute_optimal_sleep(d)

    if att < 75:
        impact = "⚠️ Continuing current habits will likely result in attendance shortage & academic penalties."
    elif att < 85:
        impact = "🟡 Moderate risk. Small improvements in sleep can significantly raise your attendance."
    else:
        impact = "✅ Current habits support good attendance. Stay consistent!"

    return PredictionResult(
        predicted_attendance=att,
        attendance_risk=ar,
        fatigue_risk=fr,
        sleep_metrics=sm,
        optimal_sleep=opt,
        habit_impact=impact,
    )


def generate_insights(d: BehavioralData, pred: PredictionResult) -> list:
    ins = []
    if d.sleep_duration < 6:
        ins.append({"type":"warning","icon":"😴","title":"Sleep Debt Detected",
            "msg":f"Only {d.sleep_duration}h/night. Chronic deprivation reduces cognition by 25%. Target 7–9h."})
    elif d.sleep_duration >= 8:
        ins.append({"type":"success","icon":"🌙","title":"Optimal Sleep Duration",
            "msg":f"{d.sleep_duration}h supports memory & focus. Keep it up!"})

    if d.deep_sleep_percentage < 15:
        ins.append({"type":"warning","icon":"🧠","title":"Low Deep Sleep",
            "msg":f"Only {d.deep_sleep_percentage}% deep sleep. Reduce alcohol & screens before bed."})

    if d.screen_time >= 6:
        ins.append({"type":"warning","icon":"📱","title":"High Screen Exposure",
            "msg":f"{d.screen_time}h/day disrupts melatonin. Use Night Mode 1h before sleep."})

    if d.physical_activity < 2:
        ins.append({"type":"info","icon":"🏃","title":"Low Physical Activity",
            "msg":"< 2h/week exercise. Exercise improves sleep quality by up to 65%."})
    elif d.physical_activity >= 5:
        ins.append({"type":"success","icon":"💪","title":"Active Lifestyle",
            "msg":f"{d.physical_activity}h/week is excellent for sleep regulation."})

    if d.stress_level >= 8:
        ins.append({"type":"critical","icon":"⚡","title":"High Stress Alert",
            "msg":"Stress 8+/10 severely impacts sleep. Try mindfulness or journaling."})

    if pred.predicted_attendance < 75:
        ins.append({"type":"critical","icon":"🚨","title":"Attendance Shortage Risk",
            "msg":f"Predicted {pred.predicted_attendance:.1f}% is below 75% threshold. Act now."})

    if d.sleep_timing == 1:
        ins.append({"type":"warning","icon":"🌃","title":"Late Sleep Pattern",
            "msg":"Sleeping after midnight detected 5 days/week. This disrupts circadian rhythm."})
    return ins


def age_group_stats(records: list) -> dict:
    if not records: return {}
    n = len(records)
    avg_sleep  = sum(r["sleep_duration"] for r in records) / n
    avg_deep   = sum(r["deep_sleep_percentage"] for r in records) / n
    avg_study  = sum(r["study_hours"] for r in records) / n
    avg_screen = sum(r["screen_time"] for r in records) / n
    avg_stress = sum(r["stress_level"] for r in records) / n
    atts = [r["present_days"]/r["total_days"]*100 for r in records if r.get("total_days",0)>0]
    return {
        "n": n,
        "avg_sleep":      round(avg_sleep, 2),
        "avg_deep_sleep": round(avg_deep, 2),
        "avg_study":      round(avg_study, 2),
        "avg_screen_time":round(avg_screen, 2),
        "avg_stress":     round(avg_stress, 2),
        "avg_attendance": round(sum(atts)/len(atts), 2) if atts else 0,
    }


def research_stats(records: list) -> dict:
    if not records:
        return {
            "total": 0, "pct_under6h": 0, "pct_late_sleepers": 0,
            "avg_sleep": 0, "avg_attendance": 0,
            "under6_absenteeism": 28, "late_sleep_impact": 15,
            "high_screen_impact": 22, "low_exercise_impact": 18,
        }
    n = len(records)
    under6  = [r for r in records if r["sleep_duration"] < 6]
    late    = [r for r in records if r["sleep_timing"] == 1]
    hi_scr  = [r for r in records if r["screen_time"] >= 6]
    lo_ex   = [r for r in records if r["physical_activity"] < 2]

    def avg_att(recs):
        a = [r["present_days"]/r["total_days"]*100 for r in recs if r.get("total_days",0)>0]
        return round(sum(a)/len(a), 1) if a else 0

    overall_att = avg_att(records)
    under6_att  = avg_att(under6)
    late_att    = avg_att(late)
    hiscr_att   = avg_att(hi_scr)
    loex_att    = avg_att(lo_ex)

    return {
        "total": n,
        "pct_under6h":      round(len(under6)/n*100, 1),
        "pct_late_sleepers":round(len(late)/n*100, 1),
        "avg_sleep":        round(sum(r["sleep_duration"] for r in records)/n, 2),
        "avg_attendance":   overall_att,
        "under6_absenteeism": max(0, round(overall_att - under6_att, 1)) if under6 else 28,
        "late_sleep_impact":  max(0, round(overall_att - late_att, 1)) if late else 15,
        "high_screen_impact": max(0, round(overall_att - hiscr_att, 1)) if hi_scr else 22,
        "low_exercise_impact":max(0, round(overall_att - loex_att, 1)) if lo_ex else 18,
    }
