# DeliriumWatch 🏥
### Temporal Early Warning System for ICU Delirium Onset

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![MIMIC-IV](https://img.shields.io/badge/Data-MIMIC--IV%20v3.1-green.svg)](https://physionet.org/content/mimiciv/3.1/)
[![AUROC](https://img.shields.io/badge/AUROC-0.8511-brightgreen.svg)]()
[![License](https://img.shields.io/badge/License-PhysioNet%20DUA-red.svg)]()

> **Predicting ICU delirium onset before it happens — using a novel sleep disruption proxy engineered from nursing timestamp patterns in MIMIC-IV.**

---

## Table of Contents

- [Problem Statement](#problem-statement)
- [Novel Contribution](#novel-contribution)
- [Dataset](#dataset)
- [Results](#results)
- [Project Structure](#project-structure)
- [Data Pipeline](#data-pipeline)
- [Feature Engineering](#feature-engineering)
- [Methodology](#methodology)
- [Reproducing Results](#reproducing-results)
- [Ethical Considerations](#ethical-considerations)
- [Version History](#version-history)
- [Roadmap](#roadmap)
- [Team](#team)

---

## Problem Statement

ICU delirium affects **60–80% of mechanically ventilated patients**, triples 30-day mortality, increases ICU stay by 5+ days, and causes long-term cognitive impairment in 40% of survivors.

The current standard of care is reactive — bedside nurses assess patients using the CAM-ICU tool every 8–12 hours. By the time delirium is detected, the window for preventive intervention has already closed.

**We frame this as a supervised binary classification problem:**

> Given all EHR data available in the symmetric observation window, predict whether a patient will develop ICU delirium — before the first positive CAM-ICU assessment.

---

## Novel Contribution

### Nighttime Intervention Density (NID)

Every existing ICU delirium prediction paper ignores sleep disruption — not because it's unimportant, but because no EHR system directly records sleep quality.

We introduce **Nighttime Intervention Density (NID)**: a proxy for sleep fragmentation derived from the timestamps of nursing chartevents in MIMIC-IV.

```
NID = (nursing events between 22:00–06:00) / (total nursing events in observation window)
```

NID produces a normalized score between 0 and 1, representing the proportion of clinical care activity occurring during sleeping hours — comparable across patients regardless of ICU stay duration.

**Validation:**
- Delirious patients: NID mean = 0.3550
- Non-delirious patients: NID mean = 0.3338
- Mann-Whitney U test: **p < 0.0001**
- SHAP importance rank: **#1 of 27 features**
- Ablation contribution (random split): **+0.0292 AUROC**
- Ablation contribution (temporal split): **+0.0243 AUROC**

NID signal strengthened progressively across pipeline versions as confounding features were removed — from SHAP rank #4 with +0.0004 ablation in v1, to SHAP rank #1 with +0.0292 ablation in the final pipeline. This progressive strengthening validates NID as a genuine independent predictor rather than a correlated proxy.

---

## Dataset

**Source:** MIMIC-IV v3.1 (PhysioNet, MIT Laboratory for Computational Physiology)

Access requires PhysioNet credentialing and signing the MIMIC-IV Data Use Agreement. Data is available via Google BigQuery.

> ⚠️ **Important:** Per PhysioNet DUA, MIMIC-IV data must not be shared publicly, uploaded to GitHub, or transmitted to third-party AI services. This repository contains no patient data.

### Cohort Construction

| Step | Stays Remaining |
|------|----------------|
| All ICU stays with CAM-ICU assessments | 69,879 |
| After excluding UTA-only assessments | 69,879 |
| After excluding stays < 24 hours | 57,992 |
| After 12-hour minimum pre-delirium window | 48,786 |
| After symmetric window matching| **25,843** |

### Final Cohort

- Total ICU stays: **25,843**
- Delirium positive: 11,815 (45.7%)
- Delirium negative: 14,028 (54.3%)
- Class ratio: 1:1.19 — near perfectly balanced
- Mean observation window: 59 hours
- Min window: 12 hours, Max window: 1,321 hours
- ICU types: 10 (MICU, SICU, CVICU, CCU, TSICU, Neuro SICU, Neuro Intermediate, Neuro Stepdown, PACU, Other)

### Temporal Distribution

| Year Group | Stays | Delirium Rate | Split |
|------------|-------|---------------|-------|
| 2008–2010 | 4,307 | 45.0% | Train |
| 2011–2013 | 5,647 | 44.1% | Train |
| 2014–2016 | 6,086 | 48.3% | Train |
| 2017–2019 | 5,592 | 45.1% | Test |
| 2020–2022 | 4,211 | 45.7% | Test |

Consistent delirium rates across all year groups confirms no label drift — temporal split is clean and fair.

### Label Extraction

Delirium labels extracted from `mimiciv_icu.chartevents` using itemid `228332` (Delirium Assessment):
- `Positive` → delirium label = 1, timestamp = first positive assessment
- `Negative` → delirium label = 0
- `UTA` (Unable to Assess) → excluded

---

## Results

### Model Performance

| Model | Validation | AUROC | Delirium Recall | Accuracy |
|-------|-----------|-------|-----------------|----------|
| Published benchmark | — | 0.79 | — | — |
| Logistic Regression | Random split | 0.7655 | 0.68 | 0.70 |
| XGBoost | Random split | 0.8405 | 0.73 | 0.76 |
| **XGBoost** | **Temporal split** | **0.8511** | **0.67** | **0.77** |

XGBoost achieves higher AUROC on temporal split (0.8511) than random split (0.8405), demonstrating the model captures stable clinical relationships rather than time-specific artifacts.

### SHAP Feature Importance — Top 10 (Temporal Split)

| Rank | Feature | Category |
|------|---------|----------|
| **1** | **nid_score** | **Novel — sleep disruption proxy** |
| 2 | avg_sofa | Clinical severity |
| 3 | age | Demographics |
| 4 | propofol_total | Sedation pharmacology |
| 5 | spo2_min | Vitals |
| 6 | icu_Medical Intensive Care Unit (MICU) | ICU type |
| 7 | nibp_mean | Vitals |
| 8 | rr_mean | Vitals |
| 9 | unique_sedation_drugs | Sedation complexity |
| 10 | fentanyl_total | Sedation pharmacology |

### NID Ablation Study

| Validation | With NID | Without NID | Delta |
|-----------|----------|-------------|-------|
| Random split | 0.8405 | 0.8113 | **+0.0292** |
| Temporal split | 0.8511 | 0.8268 | **+0.0243** |

NID contributes meaningfully on both validation strategies, confirming the feature is not overfitting to the random split.

---

## Project Structure

```
deliriumwatch/
│
├── sql/                               # BigQuery extraction queries
│   ├── 01_labels.sql                  # CAM-ICU label extraction
│   ├── 02_cohort.sql                  # ICU stay demographics
│   ├── 03_cohort_v2.sql               # 12-hour minimum window filter
│   ├── 04_anchor_pathb.sql            # Symmetric window anchors
│   ├── 05_vitals_pathb.sql            # Pre-window vitals
│   ├── 06_sedation_pathb.sql          # Pre-window sedation (no dex)
│   ├── 07_nid_pathb.sql               # Nighttime Intervention Density
│   ├── 08_sofa_pathb.sql              # SOFA scores within window
│   ├── 09_master_features_pathb.sql   # Joined feature table
│   └── 10_master_features_final.sql   # Final table with year groups
│
├── notebooks/
│   ├── deliriumwatch_eda.ipynb              # EDA pipeline
│   ├── deliriumwatch_model.ipynb            # Random split model
│   └── deliriumwatch_model_temporal.ipynb   # Temporal split — primary
│
├── .gitignore                         # Excludes all CSV/patient data
├── CONTEXT.md                         # Session continuity file
└── README.md
```

---

## Data Pipeline

All data extraction is performed via Google BigQuery on the PhysioNet-hosted MIMIC-IV dataset. No data is stored locally beyond the final cohort CSV (excluded from version control).

### Pipeline Overview

```
MIMIC-IV (BigQuery)
        │
        ├── chartevents (itemid 228332) ──► labels table
        │                                   (delirium onset timestamp)
        ├── icustays + patients ──────────► cohort tables
        │                                   (demographics, ICU type,
        │                                    anchor_year_group)
        ├── sofa (derived) ───────────────► sofa_pathb
        │   [within window only]             (avg, max, admission SOFA)
        ├── chartevents (vitals) ─────────► vitals_pathb
        │   [within window only]             (HR, RR, SpO2, BP)
        ├── inputevents (drugs) ──────────► sedation_pathb
        │   [within window, no dex]          (propofol, midazolam, etc.)
        └── chartevents (timestamps) ─────► nid_pathb
            [within window only]             (NID score)
                    │
                    ▼
            master_features_pathb (25,843 rows)
                    │
                    ▼
            + anchor_year_group join
                    │
                    ▼
            master_features_final
                    │
                    ▼
            EDA → Temporal Split → XGBoost → SHAP → Ablation
```

### Critical Design Decisions

**Symmetric window matching**
Negative class observation windows are matched to the mean positive class duration of 59 hours starting from ICU admission. Without this, negative class used entire ICU stay (mean 179 hours) vs positive class pre-delirium window (mean 59 hours) — a 3x asymmetry that biased the model toward learning stay duration rather than clinical features.

**Minimum 12-hour observation window**
Patients with less than 12 hours of observation data are excluded. Without this filter, NID becomes artifactually inflated — a patient admitted at 11pm assessed at 2am has NID = 1.0 purely by window timing. After filtering, 9 patients (0.017%) have NID > 0.95 — acceptable as genuinely nocturnal care patterns.

**Dexmedetomidine excluded**
Audit of 5,420 dexmedetomidine-receiving delirious patients showed 67.3% received the drug AFTER delirium onset (avg +29 hours post-delirium). Dexmedetomidine is prescribed TO TREAT delirium — including it constitutes reverse causality.

**Propofol temporal audit**
74.9% of propofol administration occurred before delirium onset (avg -22.6 hours pre-delirium). Retained but restricted strictly to pre-window timestamps to exclude reactive dosing.

**Temporal validation using anchor_year_group**
MIMIC-IV's anchor_year_group preserves relative temporal ordering despite date-shifting for privacy. Train: 2008–2016 (16,040 stays). Test: 2017–2022 (9,803 stays). Validates robustness to clinical protocol drift across 15 years of admissions.

---

## Feature Engineering

### Features Used in Final Model (27 features)

**Demographics (3)**
| Feature | Description | Encoding |
|---------|-------------|----------|
| age | Patient age at admission | Continuous |
| gender | Patient sex | Label encoded (M=0, F=1) |
| first_careunit | ICU type | One-hot (10 categories, rare < 100 → Other) |

**Clinical Severity (2)**
| Feature | Description | Notes |
|---------|-------------|-------|
| avg_sofa | Mean SOFA score within window | Full trajectory |
| admission_sofa | SOFA at ICU admission | Baseline severity |

**Vitals — within window (9)**
| Feature | Bounds |
|---------|--------|
| hr_mean | 20–300 bpm |
| hr_std | 0–50 |
| rr_mean | 4–60 breaths/min |
| rr_std | 0–15 |
| spo2_mean | 50–100% |
| spo2_min | 50–100% |
| nibp_mean | 20–200 mmHg |
| abp_measured | Binary flag (arterial line present) |

**Sedation — pre-window only, no dexmedetomidine (5)**
| Feature | Description |
|---------|-------------|
| propofol_total | Cumulative dose in window |
| midazolam_total | Cumulative dose in window |
| lorazepam_total | Cumulative dose in window |
| fentanyl_total | Cumulative dose in window |
| unique_sedation_drugs | Count of distinct sedation agents |

**Novel Feature (1)**
| Feature | SHAP Rank | Ablation | p-value |
|---------|-----------|----------|---------|
| nid_score | **#1** | **+0.0243** | **< 0.0001** |

### Features Dropped and Why

| Feature | Reason |
|---------|--------|
| subject_id, stay_id | IDs |
| window_hours | Leakage — positive variable, negative fixed at 59 |
| anchor_year_group | Temporal split variable only |
| icu_los_hours | Leakage — known only post-discharge |
| night_interventions, day_interventions | Raw counts, stay-length confounded |
| max_sofa | 0.95 corr with avg_sofa |
| hr_min | 0.83 corr with hr_mean |
| hr_max | 0.73 corr with hr_mean |
| abp_mean | 0.85 corr with abp_measured (57.8% imputed) |
| nibp_min | 0.69 corr with nibp_mean |
| night_day_ratio | 0.98 corr with nid_score |
| dexmedetomidine_total | 67.3% post-delirium — reverse causality |
| admission_sofa | 0.92 corr with avg_sofa |

---

## Methodology

### EDA Pipeline

1. Shape and dtype inspection
2. Save anchor_year_group before dropping
3. Leakage audit — drop unavailable-at-prediction-time columns
4. Missing value analysis — median imputation for vitals, 0 for sedation
5. Physiological bounds clipping — clinical limits, not statistical IQR
6. Distribution analysis — per-class histograms
7. Correlation matrix — drop features with |r| > 0.70
8. Categorical encoding — label encode binary, one-hot encode multi-class

### Reverse Causality Audit

| Drug | % Before Delirium | % After Delirium | Decision |
|------|-------------------|------------------|----------|
| Propofol | 74.9% | 18.0% | Keep, pre-window only |
| Midazolam | ~75% | ~18% | Keep, pre-window only |
| Lorazepam | ~75% | ~18% | Keep, pre-window only |
| Fentanyl | ~75% | ~18% | Keep, pre-window only |
| **Dexmedetomidine** | **29.7%** | **67.3%** | **Dropped** |

### Modeling

**Temporal train/test split:**
- Train: 2008–2010, 2011–2013, 2014–2016 → 16,040 stays
- Test: 2017–2019, 2020–2022 → 9,803 stays

**Class imbalance:** `scale_pos_weight = 14028/11815 = 1.19`

**XGBoost configuration:**
```python
XGBClassifier(
    n_estimators=300, max_depth=6,
    learning_rate=0.05, subsample=0.8,
    colsample_bytree=0.8,
    scale_pos_weight=1.19,
    random_state=42
)
```

**Primary metric:** AUROC | **Secondary:** AUPRC, F1, delirium recall

---

## Reproducing Results

### Prerequisites

```bash
pip install pandas numpy matplotlib seaborn scikit-learn xgboost shap optuna scipy imbalanced-learn
```

### Steps

1. Complete PhysioNet credentialing and request MIMIC-IV BigQuery access
2. Create BigQuery dataset `deliriumwatch`
3. Run SQL files 01–10 in order, replacing project ID
4. Download `master_features_final` as CSV
5. Run `deliriumwatch_eda.ipynb` — produces `deliriumwatch_clean_final.csv` and `year_groups.csv`
6. Run `deliriumwatch_model_temporal.ipynb` — reproduces AUROC 0.8511

> ⚠️ Never commit CSV files. `.gitignore` excludes all patient data.

## Web UI Demo (Flask)

This repository now includes a lightweight web interface for demos:

- Path: `flask/app.py`
- Purpose: single-patient risk preview + batch CSV inference
- Modes:
        - Model mode (if `deliriumwatch_ensemble.pkl` is present)=
### Run

```bash
cd flask
pip install -r requirements.txt
streamlit run app.py
```
---

## Ethical Considerations

**Data privacy:** De-identified MIMIC-IV data under PhysioNet DUA. No patient data in repository or transmitted to AI services.

**Clinical deployment:** Research prototype only. Requires IRB approval and prospective validation before any clinical use.

**Limitations:**
- Single-center data (BIDMC, Boston) — generalizability uncertain
- CAM-ICU has nursing compliance gaps
- NID is a proxy, not direct sleep measurement
- Negative class fixed at 59 hours — patients developing delirium after hour 59 misclassified (conservative bias)
- Vitals are summary statistics — temporal trajectory not captured
- 6-hour washout period not yet implemented

**Fairness:** Demographic stratification planned as next milestone.

---

## Version History

| Version | Cohort | AUROC | Issue / Change |
|---------|--------|-------|----------------|
| v1 | 57,992 | 0.8689 | Full stay window — leakage |
| v2 | 57,992 | 0.9398 | Short window NID artifact |
| v3 | 48,786 | 0.8947 | Asymmetric negative class |
| optc | 52,649 | 0.7443 | Fixed 12hr window — destroyed NID |
| **random** | **25,843** | **0.8405** | **Symmetric windows, clean** |
| **temporal** | **25,843** | **0.8511** | **Temporal validation — final** |

---

## Roadmap

### Completed ✅
- [x] PhysioNet + BigQuery access
- [x] Cohort extraction — 25,843 stays (Path B)
- [x] Label engineering from CAM-ICU (itemid 228332)
- [x] Reverse causality audit — dexmedetomidine excluded
- [x] Feature engineering — vitals, sedation, SOFA, NID
- [x] Symmetric window matching (Path B)
- [x] Full EDA pipeline
- [x] Logistic Regression baseline (AUROC 0.7655)
- [x] XGBoost random split (AUROC 0.8405)
- [x] SHAP analysis — NID rank #1
- [x] NID ablation (+0.0292 random, +0.0243 temporal)
- [x] Mann-Whitney U (p < 0.0001)
- [x] Temporal validation — anchor_year_group (AUROC 0.8511)

### In Progress 🔄
- [ ] 6-hour washout period (Flag 2)
- [ ] Optuna hyperparameter tuning (target 0.87+)
- [ ] Calibration curve (Brier score)
- [ ] ROC comparison plot

### Planned 📋
- [ ] Lab features (sodium, BUN, creatinine)
- [ ] Mechanical ventilation duration
- [ ] Sedation trajectory slope
- [ ] Fairness analysis
- [ ] Streamlit clinical decision support app
- [ ] Paper submission (ML4H / CHIL / AMIA 2026)

---

## Team

**Vasa Shashank, Nandan Reddy, Chethan Prakash, Venkata Saivijay Kuncham**
CSE, RVCE Bangalore (2022 scheme, 4th semester)
PhysioNet: vijay0820

---

## Citation

```
Vasa Shashank, Nandan Reddy, Chethan Prakash, Kuncham V.S. (2026).
DeliriumWatch: Temporal Early Warning System for ICU Delirium Onset
Using Nighttime Intervention Density from MIMIC-IV.
GitHub: https://github.com/Variiish06/DeliriumWatch
```

---

## Data Access

1. Complete CITI training at physionet.org
2. Request credentialed access to MIMIC-IV v3.1
3. Sign the Data Use Agreement
4. Request BigQuery access from the Files section

Full instructions: https://physionet.org/content/mimiciv/3.1/

---

*DeliriumWatch — Built on MIMIC-IV. Validated on 25,843 ICU stays across 15 years. Target: ML4H 2026.*
