# 🧹 Code Cleanup & Project Structure Guide

## ✅ Current State Assessment

Your project structure is already quite good! Here's the full analysis:

---

## 📁 Recommended Final Folder Structure

```
sleep360/
│
├── 📄 app.py                         ✅ Keep as-is (good entry point)
│
├── 📁 backend/
│   ├── 📄 __init__.py                ✅ Keep
│   ├── 📄 analysis.py                ✅ Keep (rename consideration: ml_engine.py)
│   └── 📄 database.py                ✅ Keep
│
├── 📁 templates/                     ✅ Keep all (well structured)
│   ├── base.html
│   ├── index.html
│   ├── upload.html
│   ├── dashboard.html
│   ├── attendance.html
│   ├── predictions.html
│   ├── recommendations.html
│   ├── age_insights.html
│   ├── research.html
│   └── about.html
│
├── 📁 static/
│   ├── 📁 css/
│   │   └── main.css                  ✅ Keep
│   ├── 📁 js/
│   │   └── main.js                   ✅ Keep
│   └── 📁 images/                    ⚠️ Create this folder (currently missing)
│
├── 📁 data/
│   └── .gitkeep                      ⚠️ Add this (keeps folder in git, ignores .db)
│
├── 📁 screenshots/                   ⚠️ Create this for README images
│   └── .gitkeep
│
├── 📄 README.md                      ⬅️ Use the generated one
├── 📄 requirements.txt               ⬅️ Use the generated one
├── 📄 .gitignore                     ⬅️ Use the generated one
├── 📄 LICENSE                        ⬅️ Use the generated one
└── 📄 CONTRIBUTING.md                ⬅️ Use the generated one
```

---

## 🗑️ Files to Remove Before Uploading

| File/Folder | Why Remove |
|---|---|
| `sleep360_full/{templates,static/` | ❌ Broken directory from a bad mkdir command — delete immediately |
| `sleep360_full/{templates,static/{css,js,images},backend,data}/` | ❌ Same broken directory — delete |
| `data/sleep360.db` | ❌ Don't commit the database — add to .gitignore |
| `__pycache__/` | ❌ Python bytecode — never commit |
| `venv/` | ❌ Virtual environment — never commit |

---

## 🔧 Code Improvements (app.py)

### 1. Move secret key to environment variable

**Current (bad for GitHub):**
```python
app.secret_key = "sleep360_secret_key_2024"
```

**Fix:**
```python
import os
from dotenv import load_dotenv
load_dotenv()
app.secret_key = os.environ.get("SECRET_KEY", "dev-fallback-key-change-in-production")
```

Then create a `.env` file (already in .gitignore):
```
SECRET_KEY=your-super-secret-key-here
```

### 2. Add a `config.py` for settings

```python
# config.py
import os

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-key")
    DEBUG = os.environ.get("DEBUG", "True") == "True"
    DATABASE_URL = os.environ.get("DATABASE_URL", "data/sleep360.db")
```

### 3. Add error handlers in app.py

```python
@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404

@app.errorhandler(500)
def server_error(e):
    return render_template("500.html"), 500
```

---

## 🔧 Code Improvements (analysis.py)

The ML engine is well-written. One suggestion:

### Rename for clarity (optional)

Consider renaming `analysis.py` → `ml_engine.py` to make the purpose immediately clear in a portfolio context.

---

## 🔧 Code Improvements (database.py)

### Use context managers consistently — already done ✅

Your database code uses `with get_connection() as conn:` properly throughout. 

---

## 📋 Files to ADD

| File | Purpose |
|---|---|
| `.env` | Secret keys (gitignored) |
| `data/.gitkeep` | Keeps the data/ folder in git without committing the DB |
| `screenshots/.gitkeep` | Keeps screenshots/ in git while empty |
| `static/images/.gitkeep` | Keeps images/ in git while empty |

### Create these with:
```bash
touch data/.gitkeep
touch screenshots/.gitkeep
mkdir -p static/images && touch static/images/.gitkeep
```

---

## ✅ Pre-Upload Checklist

- [ ] Delete the broken `{templates,static/` directory
- [ ] Ensure `data/sleep360.db` is in `.gitignore`
- [ ] Move `app.secret_key` to an environment variable
- [ ] Add `screenshots/` folder with actual screenshots
- [ ] Add `data/.gitkeep` so the data directory appears in GitHub
- [ ] Run `python app.py` one final time to confirm no errors
- [ ] Review README and replace `YOUR_USERNAME` with your GitHub username
- [ ] Replace `[Your Full Name]` in `LICENSE` with your real name
