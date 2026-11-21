# Machine learning: design, evaluation, honesty

## What was there before
The original "prediction model" was a hand-weighted linear formula (`50 + (sleep−4)·4 + …`) clamped to 0–100 and labelled "predicted attendance". It was never trained. The About page claimed it was *"validated against actual student attendance records, achieving a Pearson correlation of r = 0.78"*, and the Research page showed hard-coded fallback "findings" (28%, 15%, 22%). Those claims were removed.

## What it is now

### Problem framing
- **Target:** next-day fatigue, defined as self-reported daytime sleepiness ≥ 7/10. We chose this over "predicted attendance" because attendance is already known exactly (it's arithmetic, see the attendance service), while fatigue is the thing sleep actually affects and the user can report it daily. That gives the app a path to **real labels**.
- **Unit of prediction:** one user-night, using that night plus the preceding 7-day window.

### Features (`sleep360/ml/features.py`)
| Feature | Why |
|---|---|
| `sleep_hours` | Acute sleep loss |
| `sleep_hours_7d`, `sleep_debt_7d` | Cumulative restriction; debt is relative to the user's own goal |
| `bedtime_sd_7d` | Irregularity (minutes) on a wrap-safe evening scale |
| `bedtime_rel_hours` | Circadian lateness |
| `quality`, `stress` | Self-reported |
| `screen_minutes`, `caffeine_late`, `exercise_minutes` | Behavioural factors |

Missing optional fields get **fixed, documented defaults** (stress 5, screens 30, caffeine no, exercise 20), not learned means, so a user's prediction never depends on other users' data. With fewer than 3 nights in the window, irregularity is 0 and predictions are flagged `low_confidence`.

### Data (`sleep360/ml/synthetic.py`)
No real, consented student dataset was available, and public "student sleep" datasets on Kaggle are themselves largely synthetic. So we **simulate** students explicitly:
- 400 students × 60 days → 21,200 rows after a 7-day warm-up. Positive rate 32%.
- Persistent latent traits per student (chronotype, regularity, sleep need, stress baseline, screen/caffeine/exercise habits, a random intercept) → **repeated measures**.
- Weekend shifts and an exam-crunch period every 30 days.
- The label comes from a logistic model whose coefficients are listed in `GENERATIVE_COEFFICIENTS` and copied into the model card. Effect *directions* follow research (short and irregular sleep and stress increase sleepiness). *Magnitudes are assumptions.* A hinge on short sleep and a stress × short-sleep interaction add non-linearity.
- Simulated logs pass through the **same `build_features`** as real logs.

### Evaluation (`sleep360/ml/train.py`)
- **GroupKFold (5) by student.** A random row split would put the same student's days in both train and test, so the model would learn each student's traits and look better than it is.
- **Metrics:** ROC-AUC (ranking), average precision (robust to the 32/68 imbalance), Brier (calibration matters because we show probabilities), F1 and accuracy at 0.5.
- **Baselines:** base rate, and a "slept < 6h" rule.

| Model | ROC-AUC | Avg precision | Brier | F1 | Accuracy |
|---|---|---|---|---|---|
| **Logistic regression** | **0.742 ± 0.012** | 0.619 ± 0.026 | 0.179 | 0.486 | 0.739 |
| Random forest (200 trees, depth 8) | 0.739 ± 0.014 | 0.619 ± 0.029 | 0.180 | 0.458 | 0.741 |
| HistGradientBoosting | 0.740 ± 0.013 | 0.620 ± 0.030 | 0.179 | 0.472 | 0.741 |
| Rule: slept < 6h | 0.570 ± 0.016 | 0.398 | 0.222 | 0.263 | 0.715 |
| Base rate | 0.500 | 0.323 | 0.219 | 0.000 | 0.677 |

**Selection rule:** highest mean ROC-AUC, but a simpler model wins if it's within 0.005. All three models are within each other's standard deviation, so **logistic regression** is selected. It's calibrated by construction and its explanations are easy to reason about. Tree models get isotonic calibration if they win.

**Why the ceiling is ~0.74:** the per-student random effect (SD 0.6 on the log-odds scale) and Bernoulli label noise are unobservable by design. A model that scored 0.95 on this data would indicate leakage.

**Global importance** (permutation, ROC-AUC drop on held-out students): 7-day sleep debt 0.158 ≫ stress 0.033 > quality 0.014 > 7-day mean 0.010 ≈ last night 0.010 > caffeine 0.006 > others. Debt dominates because it summarises the hinge effect across the week. Correlated features (last night, 7-day mean, debt) share credit, which is a known limitation of permutation importance.

### Explainability (`sleep360/ml/predictor.py`)
For each prediction, every feature is swapped in turn for the training median, and we record how much the probability changes. The UI shows the top 6 as signed bars ("+9 points from sleep quality"), with the user's value next to the typical value. These are local what-if effects: model-agnostic and intuitive, but **not additive and not causal**, and the UI says so.

### Serving
- The model is loaded once per process (thread-safe cache) and degrades gracefully: if the artifact is missing or incompatible, scores still work and the fatigue card shows a "model unavailable" state.
- Each `risk_assessment` row stores `model_version`, so history stays interpretable after retraining.
- `scikit-learn` is pinned because joblib pickles aren't portable across versions. `flask ml train` regenerates the artifact in about 15 seconds.

### Retraining on real data
```bash
flask --app wsgi ml train --source db   # non-demo users who logged daytime sleepiness
flask --app wsgi assess backfill        # rescore history with the new model
```
Guards: ≥ 200 labelled rows, ≥ 10 users, both classes present. CV remains grouped by user.

### Responsible-use checklist
- [x] Synthetic data disclosed on the dashboard, insights, model page, PDF and assistant prompt
- [x] No medical or diagnostic language. Wellness framing and doctor/counsellor referral.
- [x] Crisis language bypasses the model and LLM entirely
- [x] Baselines reported next to models
- [x] Grouped CV, so no identity leakage
- [ ] Real-data validation (requires consented collection)
- [ ] Fairness analysis across demographics (no demographic data is collected, by design)
