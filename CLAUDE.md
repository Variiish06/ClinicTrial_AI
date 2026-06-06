# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**DeliriumWatch** is a machine learning system for early ICU delirium prediction. It combines MIMIC-IV data pipelines, XGBoost/ensemble models, a Flask web UI, and Raspberry Pi e-ink pagers for bedside alerts.

## Running the Application

```bash
# Install Flask UI dependencies
cd flaskui
pip install -r requirements.txt

# Run the web UI (http://localhost:5050)
python app.py
```

Root-level ML dependencies (for notebooks/scripts):
```bash
pip install pandas numpy matplotlib seaborn scikit-learn xgboost shap optuna scipy imbalanced-learn
```

## Model Verification Scripts

```bash
python test_probs.py        # Verify model inference on test cases
python get_pipeline.py      # Load models and check types
python calibrate_test.py    # Model calibration verification
```

## Architecture

The system has three layers:

**1. Research Layer** — BigQuery SQL (`sql/`) extracts MIMIC-IV data. Jupyter notebooks handle EDA → preprocessing → model training:
- `Deliriumwatch_Eda.ipynb` → clean CSV
- `Deliriumwatch_Model_TV.ipynb` → primary temporal validation model (AUROC 0.8511)
- `Deliriumwatch_Model.ipynb` → random split baseline
- `Deliriumwatch_Model_EL.ipynb` → ensemble variant

**2. Model Layer** — XGBoost primary model, Logistic Regression baseline, voting ensemble. Pickled as `xgb_model.pkl`, `lr_model.pkl`, `deliriumwatch_ensemble.pkl`, `feature_names.pkl` (excluded from git). `feature_names.pkl` must be loaded in the correct order for inference.

**3. Web UI + IoT Layer** (`flaskui/`):
- `app.py` — Flask app (port 5040): form/batch prediction, SHAP explainability, ward roster, MQTT pager dispatch
- `rpi_pager.py` — Raspberry Pi daemon for Waveshare 2.13" e-ink display, subscribes to MQTT alerts
- `templates/index.html` + `static/app.js` / `style.css` — Bootstrap frontend with live telemetry canvas

**Data flow**: BigQuery SQL → Jupyter notebooks → pickled models → Flask (feature engineering + inference + SHAP) → MQTT broker → zone-assigned Raspberry Pi pagers

## Key Design Decisions

**NID (Nighttime Intervention Density)**: Novel feature derived from nursing event timestamps (22:00–06:00) as a proxy for sleep fragmentation. SHAP rank #1, +0.0243 AUROC ablation — do not remove without re-validating.

**Temporal split**: Train 2008–2016 (16,040 stays), test 2017–2022 (9,803 stays) using `anchor_year_group`. This is intentional — preserves temporal order through MIMIC-IV's privacy-shifted dates.

**Symmetric window matching**: Negative-class observation windows are fixed at 59 hours (mean positive class duration). Changing this breaks the cohort balance.

**Dexmedetomidine excluded**: 67.3% post-delirium onset → reverse causality. Propofol retained with pre-window restriction.

**Calibration bias correction**: Flask applies a logit intercept shift of −1.38 log-odds to counter `scale_pos_weight=1.19` inflation. Risk thresholds: HIGH ≥65%, MEDIUM ≥40%, LOW <40%.

## MQTT / Pager Configuration

```bash
# Environment variables for pager daemon
DW_MQTT_BROKER=127.0.0.1    # MQTT broker host
PAGER_ID=doc2                # Pager identity
PAGER_ZONE="Bay A"           # Zone assignment
```

MQTT topics: `deliriumwatch/pager/{PAGER_ID}/alerts`, `.../status`, `.../rssi`

Systemd service: `flaskui/delirium-pager-doc2.service`

## Data & Privacy

Patient data (`.csv`, `.xlsx`, `data/`) and model files (`.pkl`) are excluded from git. The project operates under PhysioNet DUA — no patient data should ever be committed. MIMIC-IV access requires PhysioNet credentials + BigQuery project setup.
