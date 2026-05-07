# 🤝 Contributing to Sleep360

Thank you for your interest in contributing to Sleep360! This document explains how to get involved.

---

## 📋 Table of Contents

- [Code of Conduct](#code-of-conduct)
- [How to Contribute](#how-to-contribute)
- [Development Setup](#development-setup)
- [Branch Naming](#branch-naming)
- [Commit Message Format](#commit-message-format)
- [Pull Request Guidelines](#pull-request-guidelines)
- [Reporting Bugs](#reporting-bugs)
- [Suggesting Features](#suggesting-features)

---

## 📜 Code of Conduct

Be respectful, inclusive, and constructive. All contributors are expected to maintain a welcoming and harassment-free environment.

---

## 🚀 How to Contribute

1. **Fork** this repository
2. **Clone** your fork locally
   ```bash
   git clone https://github.com/YOUR_USERNAME/sleep360.git
   cd sleep360
   ```
3. **Create a virtual environment** and install dependencies
   ```bash
   python -m venv venv
   source venv/bin/activate   # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```
4. **Create a new branch** for your feature/fix
   ```bash
   git checkout -b feature/your-feature-name
   ```
5. **Make your changes** and test them locally
6. **Commit** your changes with a clear message
7. **Push** to your fork and open a **Pull Request**

---

## 🛠️ Development Setup

```bash
# Run the app in development mode
python app.py

# The app will be available at http://localhost:5000
# The SQLite DB is auto-created in /data/sleep360.db
```

### Project Layout

| File/Folder | Your changes go here when... |
|---|---|
| `backend/analysis.py` | Improving the ML prediction model or adding new algorithms |
| `backend/database.py` | Adding new tables, queries, or data operations |
| `app.py` | Adding new routes or API endpoints |
| `templates/` | Modifying or adding HTML pages |
| `static/css/` | Updating styles or adding new themes |
| `static/js/` | Adding frontend interactivity or charts |

---

## 🌿 Branch Naming

Use descriptive branch names:

```
feature/add-scikit-model       # New feature
fix/dashboard-chart-bug        # Bug fix
docs/update-api-reference      # Documentation only
refactor/clean-database-layer  # Code refactoring
test/add-prediction-tests      # Adding tests
```

---

## ✅ Commit Message Format

Follow the **Conventional Commits** standard:

```
<type>: <short description>

[optional body]
```

**Types:**
- `feat:` — New feature
- `fix:` — Bug fix
- `docs:` — Documentation changes
- `style:` — Formatting, no logic change
- `refactor:` — Code restructure without behavior change
- `test:` — Adding or updating tests
- `chore:` — Build process or dependency updates

**Examples:**
```
feat: add Random Forest model for attendance prediction
fix: correct sleep score calculation for edge cases
docs: add API examples to README
```

---

## 📬 Pull Request Guidelines

- Keep PRs **small and focused** — one feature or fix per PR
- Write a clear **PR description** explaining what and why
- Reference any related **issue numbers** (e.g., `Closes #12`)
- Ensure the app runs without errors before submitting
- Add or update documentation if your change introduces new behavior

---

## 🐛 Reporting Bugs

Open a GitHub Issue with:
1. **Title** — Short description of the bug
2. **Steps to reproduce** — How to trigger the bug
3. **Expected vs actual behavior**
4. **Environment** — OS, Python version, browser

---

## 💡 Suggesting Features

Open a GitHub Issue with the label `enhancement` and describe:
- What problem the feature solves
- Proposed implementation approach (if you have one)
- Why it fits the project's goals

---

## 📂 Areas That Need Help

- 🧪 Writing unit tests (`pytest`)
- 🤖 Upgrading the ML model to use `scikit-learn`
- 🔐 Implementing proper JWT authentication
- ☁️ Setting up deployment configuration (Render / Railway)
- 📱 Building a REST API + React frontend
- 🌐 Adding i18n / language support

---

*Thank you for contributing to Sleep360! 🌙*
