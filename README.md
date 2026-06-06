# DeliriumWatch 🏥
### Critical Edge AI for ICU Delirium Prevention

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![MIMIC-IV](https://img.shields.io/badge/Data-MIMIC--IV%20v3.1-green.svg)](https://physionet.org/content/mimiciv/3.1/)
[![AUROC](https://img.shields.io/badge/AUROC-0.8511-brightgreen.svg)]()
[![Hack4SOC](https://img.shields.io/badge/Hack4SOC-3.0-purple.svg)]()
[![Qualcomm](https://img.shields.io/badge/Sponsor-Qualcomm-blue.svg)]()
[![License](https://img.shields.io/badge/License-PhysioNet%20DUA-red.svg)]()

> **A closed-loop clinical AI system that predicts ICU delirium before onset, explains why, recommends nursing interventions, generates LLM-powered alerts, and delivers them to bedside Raspberry Pi pagers — autonomously.**

---

## Hack4SOC 3.0 — Qualcomm | RVCE | June 5–6, 2026

**Theme:** Where Technology Meets Humanity

**Track:** Healthcare & Social Impact

**Team:** Shrinidhi S Rao · Nandan Reddy · Deepak U Yaliwal · Vijay Kuncham

**Institution:** RV College of Engineering, Bangalore

---

## The Problem

ICU delirium affects **60–80% of mechanically ventilated patients**. It triples 30-day mortality, adds 5+ days to ICU stay, and causes long-term cognitive impairment in 40% of survivors.

Current detection is **manual and reactive** — nurses run the CAM-ICU assessment every 8–12 hours. By the time delirium is flagged, the intervention window has closed.

**DeliriumWatch makes it predictive and automated.**

---

## What We Built

A 4-step autonomous clinical agent that runs end-to-end without human intervention:

```
MIMIC-IV (25,843 ICU stays)
        │
        ▼
┌─────────────────────────────┐
│  Step 1: Risk Assessment    │  XGBoost/LightGBM/CatBoost ensemble
│  AUROC 0.8511               │  → risk score + HIGH/MEDIUM/LOW level
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│  Step 2: SHAP Explanation   │  Why is this patient high risk?
│  NID = #1 feature           │  → top risk + protective factors
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│  Step 3: Intervention Plan  │  What can nurses actually change?
│  Modifiable vs fixed risks  │  → actionable nursing checklist
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│  Step 4: Alert Generation   │  Groq Llama 3.1 generates structured
│  + Edge Delivery            │  clinical alert → MQTT → Pi pager
└─────────────────────────────┘
```

**If risk is HIGH → alert fires automatically to the bedside Raspberry Pi Zero 2W with Waveshare 2.13" e-ink display.**

---

## Novel Contribution: NID Feature

Every existing ICU delirium paper ignores sleep disruption — not because it's unimportant, but because no EHR directly records sleep quality.

We introduce **Nighttime Intervention Density (NID)**:

```
NID = (nursing events between 22:00–06:00) / (total nursing events in window)
```

A proxy for sleep fragmentation derived from nursing timestamp patterns in MIMIC-IV.

| Metric | Value |
|--------|-------|
| SHAP importance rank | **#1 of 27 features** |
| Ablation contribution | **+0.0243 AUROC** |
| Mann-Whitney U p-value | **< 0.0001** |
| Delirious patients NID mean | 0.3550 |
| Non-delirious NID mean | 0.3338 |

---

## System Architecture

```
Flask Web UI (port 5050)
        │
        ├── /agent          →  4-step agentic pipeline UI
        ├── /               →  ward roster + batch prediction
        └── /api/agent/run  →  POST endpoint → runs full pipeline
                │
                ├── agent.py
                │     ├── assess_risk()       XGBoost ensemble
                │     ├── explain_patient()   SHAP TreeExplainer
                │     ├── plan_interventions() modifiable action map
                │     └── generate_alert()    Groq llama-3.1-8b-instant
                │
                └── MQTT publish → broker (172.20.10.2:1883)
                                        │
                                        ▼
                              Raspberry Pi Zero 2W
                              rpi_pager.py daemon
                              Waveshare 2.13" e-ink
                              (systemd auto-restart)
```

**Data flow:** BigQuery → Jupyter notebooks → pickled ensemble → Flask → SHAP → Groq → MQTT → Pi pager

---

## Model Performance

| Model | Validation | AUROC | Recall |
|-------|-----------|-------|--------|
| Published benchmark | — | 0.79 | — |
| Logistic Regression | Random split | 0.7655 | 0.68 |
| XGBoost | Random split | 0.8405 | 0.73 |
| **Voting Ensemble** | **Temporal split** | **0.8511** | **0.67** |

Trained on 2008–2016 (16,040 stays), tested on 2017–2022 (9,803 stays) — temporal validation that mirrors real deployment across 15 years of clinical data.

---

## Dataset

**MIMIC-IV v3.1** — de-identified ICU EHR from Beth Israel Deaconess Medical Center, Boston. Accessed via PhysioNet + Google BigQuery under Data Use Agreement.

| Cohort step | Stays |
|-------------|-------|
| All ICU stays with CAM-ICU assessments | 69,879 |
| After minimum 24-hour ICU stay | 57,992 |
| After 12-hour minimum pre-delirium window | 48,786 |
| After symmetric window matching | **25,843** |

- Delirium positive: 11,815 (45.7%)
- Delirium negative: 14,028 (54.3%)
- Mean observation window: 59 hours

> ⚠️ Per PhysioNet DUA, no patient data is stored in this repository.

---

## Key Design Decisions

**Symmetric window matching** — Negative class windows fixed at 59 hours (mean positive class duration). Without this, model learns stay duration, not clinical features.

**Dexmedetomidine excluded** — 67.3% of dex administration occurred post-delirium onset. It treats delirium, not predicts it. Including it = reverse causality.

**Temporal validation** — Uses MIMIC-IV's `anchor_year_group` to preserve temporal order despite date-shifting for privacy. Validates robustness to 15 years of clinical protocol drift.

**Calibration bias correction** — Flask applies logit intercept shift of −1.38 log-odds to counter `scale_pos_weight=1.19` inflation. Risk thresholds: HIGH ≥65%, MEDIUM ≥40%, LOW <40%.

---

## Hardware Stack

| Component | Spec |
|-----------|------|
| Edge device | Raspberry Pi Zero 2W |
| Display | Waveshare 2.13" e-ink (122×250) |
| Protocol | MQTT over WiFi (paho-mqtt) |
| Broker | Mosquitto 2.1.2 |
| Service | systemd daemon (auto-restart) |
| Alert topics | `deliriumwatch/pager/{id}/alerts` |

---

## Running Locally

```bash
# Install dependencies
cd flaskui
pip install -r requirements.txt

# Set environment
cp .env.example .env
# Add GROQ_API_KEY to .env

# Run
python app.py
# → http://localhost:5050
# → http://localhost:5050/agent  (4-step agent UI)
```

**Pi pager setup:**
```bash
# On Raspberry Pi
sudo systemctl enable delirium-pager-doc2
sudo systemctl start delirium-pager-doc2
# Subscribes to MQTT, renders alerts on e-ink display
```

---

## MQTT Configuration

```bash
DW_MQTT_BROKER=172.20.10.2   # Broker host (Pi)
PAGER_ID=doc2                 # Pager identity
PAGER_ZONE="Bay A"            # Zone assignment
GROQ_API_KEY=your_key_here    # For LLM alert generation
```

Topics: `deliriumwatch/pager/{id}/alerts` · `.../status` · `.../rssi` · `.../clear`

---

## Project Structure

```
deliriumwatch/
├── sql/                          # BigQuery extraction (10 queries)
├── notebooks/                    # EDA + model training
│   ├── Deliriumwatch_Eda.ipynb
│   ├── Deliriumwatch_Model_TV.ipynb    # primary (AUROC 0.8511)
│   ├── Deliriumwatch_Model_EL.ipynb   # ensemble variant
│   └── Deliriumwatch_Agent.ipynb      # agent prototype
├── flaskui/
│   ├── app.py                    # Flask app (port 5050)
│   ├── agent.py                  # 4-step agentic pipeline
│   ├── rpi_pager.py              # Pi e-ink pager daemon
│   ├── delirium-pager-doc2.service  # systemd service
│   ├── templates/
│   │   ├── index.html            # ward roster + batch prediction
│   │   └── agent.html            # 4-step agent UI
│   └── static/
│       ├── app.js
│       └── style.css
└── README.md
```

---

## Ethical Considerations

**Data privacy:** De-identified MIMIC-IV data under PhysioNet DUA. No patient data in repository or transmitted externally.

**Clinical scope:** Research prototype. Requires IRB approval and prospective validation before clinical deployment.

**Limitations:**
- Single-center data (BIDMC, Boston) — generalizability uncertain
- CAM-ICU has nursing compliance gaps
- NID is a proxy, not direct sleep measurement
- Demo uses simulated vitals — not live EHR integration
- 6-hour post-sedation washout period not yet implemented

**Deployment path:** EHR/FHIR integration → prospective validation → regulatory review

---

## Roadmap

### Completed ✅
- MIMIC-IV BigQuery pipeline (25,843 ICU stays)
- NID feature engineering (SHAP #1, p < 0.0001)
- XGBoost + ensemble model (AUROC 0.8511, temporal validation)
- SHAP explainability layer
- Groq Llama agentic alert generation
- Flask web UI (ward roster, batch prediction, agent page)
- Raspberry Pi Zero 2W e-ink pager (MQTT, systemd)
- Full closed-loop demo: UI → ML → LLM → MQTT → Pi

### Next Steps 📋
- 6-hour post-sedation washout period
- Lab features (sodium, BUN, creatinine)
- FHIR/EHR integration for live data
- Prospective validation study
- Paper submission (ML4H / CHIL / AMIA 2026)

---

## Team

| Name | Role |
|------|------|
| **Vijay Kuncham** | ML pipeline, model training, Flask backend, agent system |
| **Shrinidhi S Rao** | Frontend, UI/UX, Flask templates |
| **Nandan Reddy** | Data engineering, BigQuery SQL, feature engineering |
| **Deepak U Yaliwal** | IoT layer, Raspberry Pi pager, MQTT infrastructure |

**RV College of Engineering, Bangalore — CSE, 2022 scheme**

PhysioNet: vijay0820 · GitHub: [Variiish06/DeliriumWatch](https://github.com/Variiish06/DeliriumWatch)

---

## Citation

```
Kuncham V.S., Rao S.S., Reddy N., Yaliwal D.U. (2026).
DeliriumWatch: Agentic ICU Delirium Early Warning System
with Edge Alert Delivery. Hack4SOC 3.0, RVCE Bangalore.
GitHub: https://github.com/Variiish06/DeliriumWatch
```

---

*Built on MIMIC-IV. Validated on 25,843 ICU stays across 15 years. Delivered to the bedside in real time.*
