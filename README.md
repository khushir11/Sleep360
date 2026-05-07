<div align="center">

# 🌙 Sleep360

### *Smart Sleep & Attendance Intelligence System*

[![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-3.0%2B-000000?style=for-the-badge&logo=flask&logoColor=white)](https://flask.palletsprojects.com)
[![SQLite](https://img.shields.io/badge/SQLite-003B57?style=for-the-badge&logo=sqlite&logoColor=white)](https://sqlite.org)
[![Chart.js](https://img.shields.io/badge/Chart.js-FF6384?style=for-the-badge&logo=chartdotjs&logoColor=white)](https://chartjs.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)
[![Status](https://img.shields.io/badge/Status-Active-brightgreen?style=for-the-badge)]()

<br/>

> A healthcare-focused ML web application that predicts student **attendance risk** and **fatigue levels** based on sleep behaviour, lifestyle patterns, and academic factors — delivering personalised, data-driven insights to support student well-being.

<br/>

[📸 Screenshots](#-screenshots) • [🚀 Quick Start](#-quick-start) • [🧠 ML Engine](#-machine-learning-engine) • [📁 Project Structure](#-project-structure) • [🔮 Roadmap](#-future-scope)

</div>

---

## 📌 Overview

**Sleep360** bridges the gap between **sleep science** and **student academic performance**. Students submit their sleep and lifestyle data through an interactive form with a **live prediction preview**, and the system runs a custom **multi-factor weighted model** to:

- 📊 Predict attendance percentage from 8 sleep & lifestyle inputs
- 🚨 Classify attendance shortage risk as **High / Moderate / Low**
- 😴 Assess chronic fatigue risk with actionable health recommendations
- 📈 Generate a personal **Sleep Score (0–100)**
- 🔮 Show a **Trend Projection** — how habits changes would improve attendance
- 📐 Break down each **Factor's Impact** on attendance (e.g. Late Sleep: −8.0%)
- 👥 Compare cohort-level data across **4 age bands** (14–17, 17–19, 20–22, 23+)
- 🔬 Display a **Research Dashboard** with Pearson r = 0.78 sleep-vs-attendance correlation

---

## 📸 Screenshots

### 🏠 Home — *"Smarter Sleep. Better Attendance."*
![Home Page](screenshots/01_home.jpeg)
> Hero landing page with Sleep Score card (78/100), Attendance Risk indicator (MODERATE), and AI Prediction boost widget (+12% possible).

---

### 📋 Upload Data — *Interactive Sliders with Live Preview*
![Upload Data](screenshots/02_upload.jpeg)
> Real-time prediction preview updates as sliders move. Shows sleep duration, deep sleep %, sleep quality, attendance counts — with a Quick Tips sidebar.

---

### 🔮 AI Predictions — *Factor Impact & Trend Projection*
![AI Predictions](screenshots/06_predictions.jpeg)
> AI Forecast (63% → HIGH RISK), recommended sleep (7.5h), 4-stage colour-coded trend bars (Current 63 → Mod Fix 73 → Full Opt 83 → Target 85), and per-feature attendance contribution.

---

### 📅 Attendance — *Risk Meter & Breakdown Dashboard*
![Attendance](screenshots/04_attendance.jpeg)
> Platform stats (78.5% avg, 55/70 avg days, 1.8 late arrivals), Attendance Risk Meter, risk distribution (Safe >85% / Warn 75–85% / Risk <75%), and Missed Hours Impact chart.

---

### 👥 Age Insights — *Cohort Analytics Across Age Groups*
![Age Insights](screenshots/03_age_insights.jpeg)
> Four age-group summary cards with comparative bar charts for Sleep Duration, Attendance %, Late Sleeping Trends (17–19 yr: 60% late sleepers), and Stress Levels by group.

---

### 🔬 Research — *Sleep vs Attendance Correlation*
![Research](screenshots/05_research.jpeg)
> Key findings: 33.3% sleep under 6h (CRITICAL), 66.7% late sleepers, Pearson r = 0.78 correlation chart, Habit Impact breakdown (Late Sleep −8%, High Screen −12%, Low Exercise −18%).

---

## ✨ Features

| Feature | Description |
|---|---|
| 🧠 **ML Prediction Engine** | Custom 8-feature weighted model predicts attendance % with explainable weights |
| ⚡ **Live Preview Panel** | Sliders update Sleep Score + predicted attendance in real time |
| 🔮 **Trend Projection** | 4-stage bar chart showing improvement path to target attendance |
| 📐 **Factor Impact Breakdown** | Per-feature contribution display (e.g. Sleep Duration +4.0%/hr, Late Sleep −8.0%) |
| 📊 **Personal Dashboard** | Visual charts, score history, and risk summary per student |
| 📅 **Attendance Tracker** | Present/total days, late arrivals, missed first-hour tracking |
| 💤 **Sleep Score (0–100)** | Composite score: duration (40pts) + deep sleep % (30pts) + timing (30pts) |
| 🔴 **3-Tier Risk System** | Colour-coded: Low / Moderate / High with actionable recommendations |
| 💡 **Smart Insights** | Contextual, research-backed health cards per student |
| 👥 **Age Group Analytics** | 4 age cohorts × 4 chart types: sleep, attendance, late trends, stress |
| 🔬 **Research Dashboard** | Pearson correlation, habit impact analysis, key statistical findings table |
| 🌑 **Dark Theme UI** | Polished dark interface with gradient accents and responsive layout |

---

## 🧠 Machine Learning Engine

Sleep360's engine is a **transparent, explainable model** — every weight has a scientific justification, making it ideal for portfolio and academic discussion.

### Attendance Prediction Formula

```
attendance_score = 50
  + (sleep_duration − 4) × 4.0    →  Sleep Duration:    +4.0% per extra hour
  + sleep_quality × 1.5            →  Sleep Quality:     subjective rating weight
  + deep_sleep_percentage × 0.3    →  Deep Sleep %:      +0.3% per 1% deep sleep
  − sleep_timing × 8.0             →  Late Sleep:        −8.0% penalty
  + study_hours × 2.0              →  Study Hours:       +2.0% per hour
  − screen_time × 1.5              →  Screen Time:       −1.5% per hour
  + physical_activity × 0.8        →  Physical Activity: +0.8% per hour/week
  − (stress_level − 5) × 1.2       →  Stress Level:      −1.2% above baseline
```

### Algorithms & Models

| Component | Method |
|---|---|
| **Attendance Prediction** | Weighted Linear Scoring (custom, fully explainable) |
| **Risk Classification** | Multi-threshold classifier (≥85% Low / 75–84% Moderate / <75% High) |
| **Fatigue Assessment** | Rule-based additive scoring (6 behavioural signal flags) |
| **Sleep Score** | Composite weighted formula (3 components → 0–100 scale) |
| **Trend Projection** | Scenario simulation: +10pt and +22pt improvement paths |
| **Cohort Analytics** | Segmented group aggregation with Pearson r correlation |

### Feature → Output Mapping

```
Input Features (8):             Output Predictions (4):
────────────────────            ──────────────────────────────
sleep_duration          →       predicted_attendance (0–100%)
deep_sleep_percentage   →       attendance_risk_level
sleep_timing            →       fatigue_risk_level
sleep_quality           →       sleep_score (0–100)
study_hours
screen_time
physical_activity
stress_level
```

---

## 🛠️ Technologies Used

**Backend**
- 🐍 Python 3.9+ with typed `dataclasses` for clean ML data structures
- 🌐 Flask 3.0 — web framework and RESTful API layer
- 🗄️ SQLite — zero-config relational DB, auto-created on first run

**Frontend**
- 🎨 HTML5 + CSS3 with Jinja2 templating
- ⚡ Vanilla JavaScript — live preview engine, API calls, dynamic rendering
- 📊 Chart.js — interactive bar charts across all analytics views

**Architecture**
- 🏗️ MVC-inspired: ML engine (`analysis.py`), DB layer (`database.py`), routing (`app.py`)
- 🔌 REST API with 7 JSON endpoints (`/api/*`)
- 🔐 Flask session-based authentication
- 🌱 Auto-seeded demo database with 8 realistic student profiles

---

## 📁 Project Structure

```
sleep360/
│
├── app.py                    # Flask entry point — all routes & API endpoints
│
├── backend/
│   ├── __init__.py
│   ├── analysis.py           # 🧠 ML engine: prediction, scoring, insights
│   └── database.py           # 🗄️ SQLite schema, CRUD, demo data seeding
│
├── templates/                # Jinja2 HTML templates
│   ├── base.html             # Shared dark-theme layout with navigation
│   ├── index.html            # Landing page with hero & platform stats
│   ├── upload.html           # Slider form with live prediction preview
│   ├── dashboard.html        # Personal sleep dashboard
│   ├── attendance.html       # Attendance tracker & risk meter
│   ├── predictions.html      # AI forecast, trend projection, factor impact
│   ├── recommendations.html  # Personalised health recommendation cards
│   ├── age_insights.html     # Cohort analytics (4 groups × 4 chart types)
│   ├── research.html         # Research stats & correlation analysis
│   └── about.html            # Project information
│
├── static/
│   ├── css/main.css          # Dark theme, gradient accents, responsive layout
│   ├── js/main.js            # Live preview engine, Chart.js charts, API calls
│   └── images/               # UI assets
│
├── data/
│   └── sleep360.db           # SQLite database (auto-created, gitignored)
│
├── screenshots/              # App screenshots (used in this README)
├── requirements.txt          # Python dependencies
├── .gitignore                # Python + Flask + ML gitignore
├── LICENSE                   # MIT License
├── CONTRIBUTING.md           # Contribution guidelines
└── README.md                 # This file
```

---

## 🚀 Quick Start

### Prerequisites
- Python **3.9+** — [Download](https://python.org/downloads)
- pip (bundled with Python)
- Git

### 1. Clone the Repository
```bash
git clone https://github.com/YOUR_USERNAME/sleep360.git
cd sleep360
```

### 2. Create & Activate Virtual Environment
```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Run the Application
```bash
python app.py
```

### 5. Open in Browser
```
http://localhost:5000
```

> 🎉 The database auto-creates on first run with **8 demo student profiles** pre-loaded. Sign in with any demo email (e.g. `rahul@demo.com`) to explore all features immediately.

**Demo Accounts**

| Name | Email | Profile |
|---|---|---|
| Rahul Verma | rahul@demo.com | Good sleeper, high attendance |
| Sneha Reddy | sneha@demo.com | High risk, sleep deprived |
| Dev Kapoor | dev@demo.com | Optimal sleep, best attendance |
| Rohan Das | rohan@demo.com | Critical risk, needs help |

---

## 🔌 API Reference

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/register` | Register new student |
| `POST` | `/api/login` | Sign in with email |
| `POST` | `/api/logout` | Clear session |
| `POST` | `/api/submit` | Submit sleep data + run ML prediction |
| `GET` | `/api/user-data` | Get current user's records & predictions |
| `GET` | `/api/platform-stats` | Aggregate platform statistics |
| `GET` | `/api/age-group-data` | Cohort-segmented analytics |

**Sample Request — Submit Sleep Data:**
```json
POST /api/submit
{
  "sleep_duration": 7.0,
  "deep_sleep_percentage": 18,
  "sleep_timing": 0,
  "sleep_quality": 7,
  "study_hours": 5,
  "screen_time": 3,
  "physical_activity": 4,
  "stress_level": 5
}
```

**Sample Response:**
```json
{
  "ok": true,
  "result": {
    "predicted_attendance": 87.0,
    "attendance_risk_level": "low",
    "attendance_risk_score": 3.0,
    "sleep_score": 74.4,
    "fatigue_risk_level": "low",
    "fatigue_recommendation": "✅ Good sleep hygiene! Keep it up."
  },
  "insights": [...]
}
```

---

## 🔮 Future Scope

- [ ] 🤖 **scikit-learn Upgrade** — Train Random Forest / XGBoost on real sleep study datasets
- [ ] 🔐 **JWT Authentication** — Token-based login with bcrypt password hashing
- [ ] 📱 **React Frontend** — Decouple into SPA architecture with Flask REST backend
- [ ] ☁️ **Cloud Deployment** — Deploy to Render / Railway with PostgreSQL
- [ ] 📲 **Wearable Integration** — Auto-import from Fitbit / Apple Health APIs
- [ ] 🔔 **Smart Notifications** — Alert students when attendance risk rises
- [ ] 📤 **PDF Report Export** — Generate personalised health reports (ReportLab)
- [ ] 🐳 **Docker Containerisation** — One-command `docker-compose up` deployment
- [ ] 🏫 **Faculty Admin Panel** — Institution-level analytics and intervention tools
- [ ] 📈 **Multi-week Trend Tracking** — Historical sleep timeline per student

---

## 🤝 Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

```bash
# Standard workflow
git checkout -b feature/your-feature-name
# make your changes
git commit -m "feat: describe your change"
git push origin feature/your-feature-name
# open a Pull Request
```

---

## 👩‍💻 Contributors

| Name | Role |
|---|---|
| **Khushi Rai** | Full-Stack Developer  |
| **N. Harshani  ** |   ML Designer         |

---

## 📄 License

This project is licensed under the **MIT License** — see [LICENSE](LICENSE) for details.

---

<div align="center">

Made with ❤️ for student health & academic success

⭐ **If this project helped you, please give it a star!**

</div>
