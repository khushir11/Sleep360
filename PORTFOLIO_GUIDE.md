# 🎯 Portfolio & Interview Guide — Sleep360

Use this document to describe Sleep360 in resumes, LinkedIn, and interviews.

---

## 📄 Resume Entry

```
Sleep360 — Smart Sleep & Attendance Intelligence System                     2025
• Developed a full-stack Flask web app that predicts student attendance (%) using a
  custom 8-feature weighted ML model with rule-based risk classification
• Engineered a modular backend separating ML logic, SQLite database layer, and REST
  API routes; served 8+ interactive pages via Jinja2 + Chart.js
• Designed 3-tier risk classification (High/Moderate/Low) for attendance shortage
  and fatigue, with automated personalised health insight generation
• Implemented age-group cohort analytics (14–17, 17–19, 20–22, 23+) and a
  research statistics dashboard showing behavioural impact on absenteeism
Tech: Python, Flask, SQLite, JavaScript, Chart.js, HTML/CSS, REST API
```

---

## 🔑 Key Technical Highlights (for resume bullet points)

- "Built a custom multi-factor predictive model without ML libraries to ensure full explainability and transparent scoring logic"
- "Designed and implemented a RESTful JSON API with 7 endpoints handling student data, ML inference, and session management"
- "Structured the project with an MVC-inspired architecture: separate modules for data layer, ML engine, and routing"
- "Auto-seeded database with 8 realistic demo profiles to enable immediate live exploration"
- "Implemented composite Sleep Score (0–100) using weighted sub-scores for duration, deep sleep %, and sleep timing"

---

## 🎤 Interview Explanation (30-second pitch)

> "Sleep360 is a healthcare web application I built with Flask and Python. It takes a student's sleep data — like duration, deep sleep percentage, timing, and lifestyle factors like screen time and stress — and runs them through a custom predictive model to forecast their attendance percentage. It also classifies their fatigue and attendance risk as High, Moderate, or Low, and generates personalised health recommendations. The backend is fully modular — a clean separation between the ML engine, the SQLite database layer, and the Flask routing. I also built a research dashboard with cohort-level analytics grouped by age."

---

## 💬 Common Interview Questions & Strong Answers

### "Why did you build your own ML model instead of using scikit-learn?"

> "I wanted full transparency and explainability — every weight in my prediction formula has a justifiable reason based on sleep science research. Using a custom model also helped me deeply understand what the features represent, which would have been opaque with a black-box model. As a next step, I plan to train a Random Forest using scikit-learn and compare accuracy."

### "How did you handle the ML pipeline architecture?"

> "I separated concerns clearly: `analysis.py` handles all ML logic — prediction, risk classification, fatigue scoring, and insight generation. `database.py` handles all SQLite operations. And `app.py` only contains Flask routes. Each layer communicates through typed Python dataclasses, which gives it almost a statically-typed feel."

### "What's the database schema like?"

> "Three tables: `students` for registration data, `sleep_records` for each submission with all 8 behavioral features plus attendance counts, and `predictions` storing each ML inference result. Everything uses SQLite, which makes it zero-config and easy to demo."

### "What would you improve with more time?"

> "Three things: First, replace the custom model with a trained scikit-learn Random Forest using real sleep study datasets. Second, add proper authentication with JWT tokens. Third, deploy it to Render or Railway with a PostgreSQL backend."

---

## 🏆 Technical Achievements to Highlight

| Achievement | Why It Matters |
|---|---|
| End-to-end ML pipeline | Shows you can take data → model → API → UI |
| Custom weighted model | Shows you understand the math, not just the libraries |
| Typed dataclasses | Shows Python best practices |
| REST API design | Backend engineering skill |
| Chart.js integration | Frontend data viz skill |
| SQLite schema design | Database design skill |
| Modular architecture | Software engineering maturity |
| Demo data seeding | Product thinking — "works out of the box" |

---

## 🔮 Advanced Improvements (to mention as "future scope")

| Improvement | Skill Signal |
|---|---|
| scikit-learn Random Forest upgrade | Applied ML |
| Fitbit / Apple Health API integration | External API integration |
| JWT + bcrypt authentication | Security engineering |
| Deploy to Render/Railway + PostgreSQL | DevOps / cloud |
| React + Flask REST decoupling | Full-stack architecture |
| PDF health report export (ReportLab) | File generation |
| Admin panel for faculty analytics | Role-based access control |
| Docker containerisation | DevOps / containerisation |

---

## 🔖 LinkedIn Project Description

```
🌙 Sleep360 — Smart Sleep & Attendance Intelligence System

A Flask + Machine Learning web application that predicts student attendance risk and
fatigue levels from sleep behaviour and lifestyle inputs.

Key features:
✅ Custom 8-feature ML model predicting attendance percentage
✅ 3-tier risk classification: High / Moderate / Low
✅ Personal Sleep Score (0–100) with composite scoring
✅ Age-group cohort analytics (14–17, 17–19, 20–22, 23+)
✅ RESTful JSON API with 7 endpoints
✅ Research dashboard showing behavioural absenteeism impact
✅ SQLite database with auto-seeded demo data
✅ Responsive UI with Chart.js visualisations

Tech Stack: Python · Flask · SQLite · JavaScript · Chart.js · HTML/CSS

GitHub: https://github.com/YOUR_USERNAME/sleep360
```
