import os
from dotenv import load_dotenv
load_dotenv()

import time
import json
import threading
from io import BytesIO
from typing import Dict, List, Tuple
from datetime import datetime

import joblib
import numpy as np
import pandas as pd
from flask import Flask, render_template, request, jsonify, redirect, url_for

try:
    import shap  # type: ignore
except Exception:  # optional
    shap = None

try:
    import paho.mqtt.client as mqtt
    import paho.mqtt.publish as mqtt_publish
    MQTT_AVAILABLE = True
except ImportError:
    MQTT_AVAILABLE = False

from agent import run_delirium_agent

app = Flask(__name__)

# ──────────────────────────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
XGB_PATH = os.environ.get("DW_XGB_PATH", os.path.join(BASE_DIR, "..", "xgb_model.pkl"))
LR_PATH = os.environ.get("DW_LR_PATH", os.path.join(BASE_DIR, "..", "lr_model.pkl"))
ENSEMBLE_PATH = os.environ.get("DW_ENSEMBLE_PATH", os.path.join(BASE_DIR, "..", "deliriumwatch_ensemble.pkl"))
FEATURE_NAMES_PATH = os.environ.get("DW_FEATS_PATH", os.path.join(BASE_DIR, "..", "feature_names.pkl"))

MQTT_BROKER = os.environ.get("DW_MQTT_BROKER", "127.0.0.1")
MQTT_PORT = int(os.environ.get("DW_MQTT_PORT", "1883"))

ICU_OPTIONS = [
    "Medical Intensive Care Unit (MICU)",
    "Surgical Intensive Care Unit (SICU)",
    "Cardiac Vascular Intensive Care Unit (CVICU)",
    "Coronary Care Unit (CCU)",
    "Trauma SICU (TSICU)",
    "Neuro SICU",
    "Neuro Intermediate",
    "Neuro Stepdown",
    "PACU",
    "Other",
]

ZONE_OPTIONS = ["Bay A", "Bay B", "Bay C", "Bay D"]

# Hard-coded best AUROCs from temporal notebook
METRICS = {
    "xgb": 0.8511,           # XGBoost Temporal AUROC
    "lr": 0.76,              # approx baseline
    "ensemble": 0.8526,      # Voting Ensemble Temporal AUROC
}

# Quick preset patient profiles for demo
PRESETS = {
    "high_septic": {
        "patient_name": "MARTINEZ, CARLOS",
        "patient_bed": "MICU-A-02",
        "patient_zone": "Bay A",
        "gender_select": "Male",
        "age": 78, "avg_sofa": 11.0, "admission_sofa": 9.0,
        "hr_mean": 112.0, "hr_std": 18.0, "rr_mean": 28.0, "rr_std": 6.0,
        "spo2_mean": 91.0, "spo2_min": 84.0, "nibp_mean": 62.0, "abp_measured": 1.0,
        "propofol_total": 1200.0, "midazolam_total": 25.0,
        "lorazepam_total": 8.0, "fentanyl_total": 1500.0,
        "unique_sedation_drugs": 4.0, "nid_score": 0.58,
        "icu_select": "Medical Intensive Care Unit (MICU)",
    },
    "medium_postsurg": {
        "patient_name": "JOHNSON, MARY",
        "patient_bed": "SICU-B-07",
        "patient_zone": "Bay B",
        "gender_select": "Female",
        "age": 71, "avg_sofa": 7.0, "admission_sofa": 6.0,
        "hr_mean": 98.0, "hr_std": 14.0, "rr_mean": 22.0, "rr_std": 4.5,
        "spo2_mean": 94.0, "spo2_min": 89.0, "nibp_mean": 72.0, "abp_measured": 1.0,
        "propofol_total": 600.0, "midazolam_total": 12.0,
        "lorazepam_total": 4.0, "fentanyl_total": 900.0,
        "unique_sedation_drugs": 3.0, "nid_score": 0.42,
        "icu_select": "Surgical Intensive Care Unit (SICU)",
    },
    "low_stable": {
        "patient_name": "CHEN, DAVID",
        "patient_bed": "CCU-C-01",
        "patient_zone": "Bay C",
        "gender_select": "Male",
        "age": 55, "avg_sofa": 3.0, "admission_sofa": 2.0,
        "hr_mean": 78.0, "hr_std": 8.0, "rr_mean": 16.0, "rr_std": 2.5,
        "spo2_mean": 98.0, "spo2_min": 95.0, "nibp_mean": 85.0, "abp_measured": 0.0,
        "propofol_total": 0.0, "midazolam_total": 0.0,
        "lorazepam_total": 0.0, "fentanyl_total": 200.0,
        "unique_sedation_drugs": 1.0, "nid_score": 0.22,
        "icu_select": "Coronary Care Unit (CCU)",
    },
}

# ──────────────────────────────────────────────────────────────────
# MODEL LOADING
# ──────────────────────────────────────────────────────────────────
def safe_load(path: str):
    if not path or not os.path.exists(path):
        return None
    try:
        return joblib.load(path)
    except Exception:
        return None


def load_feature_names() -> List[str]:
    feats = safe_load(FEATURE_NAMES_PATH)
    if isinstance(feats, (list, tuple)):
        return list(feats)
    return []


XGB_MODEL = safe_load(XGB_PATH)
LR_MODEL = safe_load(LR_PATH)
ENSEMBLE_MODEL = safe_load(ENSEMBLE_PATH)
FEATURE_NAMES = load_feature_names()

# ──────────────────────────────────────────────────────────────────
# TEST COHORT — loaded once at startup for agent pipeline
# ──────────────────────────────────────────────────────────────────
_DATA_CSV       = os.environ.get("DW_DATA_CSV",       os.path.join(BASE_DIR, "..", "deliriumwatch_clean_tv.csv"))
_YEAR_GROUPS_CSV = os.environ.get("DW_YEAR_GROUPS_CSV", os.path.join(BASE_DIR, "..", "year_groups.csv"))

X_test = pd.DataFrame()
y_test = pd.Series(dtype=int)
high_risk_indices: List[int] = []

try:
    _df          = pd.read_csv(_DATA_CSV)
    _year_groups = pd.read_csv(_YEAR_GROUPS_CSV)
    _X           = _df.drop(columns=["delirium_label"])
    _y           = _df["delirium_label"]
    _test_mask   = _year_groups["anchor_year_group"].isin(["2017 - 2019", "2020 - 2022"])
    X_test       = _X[_test_mask.values].reset_index(drop=True)
    y_test       = _y[_test_mask.values].reset_index(drop=True)
    print(f"Test cohort loaded: {len(X_test)} patients")
except Exception as _e:
    print(f"Could not load test cohort: {_e}")

try:
    _y_pred_proba     = ENSEMBLE_MODEL.predict_proba(X_test)[:, 1]
    high_risk_indices = [int(i) for i, p in enumerate(_y_pred_proba) if p > 0.70]
    print(f"High risk patients found: {len(high_risk_indices)}")
except Exception as _e:
    print(f"Could not compute high risk indices: {_e}")
    high_risk_indices = list(range(0, 20))


# ──────────────────────────────────────────────────────────────────
# WARD ROSTER — Thread-safe patient list
# ──────────────────────────────────────────────────────────────────
ward_lock = threading.Lock()
ward_patients: List[Dict] = []  # Each entry is a patient dict


def add_patient(patient_data: Dict):
    """Add or update a patient in the ward roster."""
    with ward_lock:
        # Update if same name+bed exists
        for i, p in enumerate(ward_patients):
            if p["name"] == patient_data["name"] and p["bed"] == patient_data["bed"]:
                ward_patients[i] = patient_data
                return
        ward_patients.append(patient_data)


def get_patients() -> List[Dict]:
    """Return all patients sorted by risk (highest first)."""
    with ward_lock:
        return sorted(ward_patients, key=lambda p: p.get("risk_raw", 0), reverse=True)


def clear_patients():
    with ward_lock:
        ward_patients.clear()


def get_risk_summary() -> Dict:
    """Count patients by risk level."""
    pts = get_patients()
    return {
        "high": sum(1 for p in pts if p.get("label") == "HIGH"),
        "medium": sum(1 for p in pts if p.get("label") == "MEDIUM"),
        "low": sum(1 for p in pts if p.get("label") == "LOW"),
        "total": len(pts),
    }


# ──────────────────────────────────────────────────────────────────
# PAGER FLEET — Track connected pagers
# ──────────────────────────────────────────────────────────────────
pager_lock = threading.Lock()
pager_fleet: Dict[str, Dict] = {}  # {pager_id: {zone, status, rssi, last_seen}}


def update_pager(pager_id: str, data: Dict):
    with pager_lock:
        existing = pager_fleet.get(pager_id, {})
        existing.update(data)
        existing["last_seen"] = time.time()
        pager_fleet[pager_id] = existing


def get_pagers() -> Dict[str, Dict]:
    """Return pager fleet with online/offline status."""
    with pager_lock:
        now = time.time()
        result = {}
        for pid, info in pager_fleet.items():
            info_copy = dict(info)
            # Offline if no heartbeat in 45 seconds
            info_copy["online"] = (now - info_copy.get("last_seen", 0)) < 45
            result[pid] = info_copy
        return result


# ──────────────────────────────────────────────────────────────────
# MQTT BACKGROUND LISTENER — heartbeats & RSSI from pagers
# ──────────────────────────────────────────────────────────────────
def start_mqtt_listener():
    """Background thread that subscribes to pager status topics."""
    if not MQTT_AVAILABLE:
        print("[MQTT] paho-mqtt not installed, skipping fleet listener.")
        return

    def on_connect(client, userdata, flags, reason_code, properties):
        print(f"[MQTT-Listener] Connected to broker — rc={reason_code}")
        client.subscribe("deliriumwatch/pager/+/status")
        client.subscribe("deliriumwatch/pager/+/rssi")

    def on_message(client, userdata, msg):
        topic_parts = msg.topic.split("/")
        if len(topic_parts) < 4:
            return
        pager_id = topic_parts[2]
        msg_type = topic_parts[3]

        try:
            payload = json.loads(msg.payload.decode())
        except Exception:
            return

        if msg_type == "status":
            update_pager(pager_id, {
                "id": pager_id,
                "zone": payload.get("zone", "Unknown"),
                "status": payload.get("status", "unknown"),
            })
        elif msg_type == "rssi":
            update_pager(pager_id, {
                "rssi": payload.get("rssi", -100),
            })

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message

    def run():
        while True:
            try:
                client.connect(MQTT_BROKER, MQTT_PORT, 60)
                client.loop_forever()
            except Exception as e:
                print(f"[MQTT-Listener] Connection failed: {e}, retrying in 5s...")
                time.sleep(5)

    t = threading.Thread(target=run, daemon=True)
    t.start()
    print("[MQTT-Listener] Background pager fleet listener started.")


# Start listener on app boot
start_mqtt_listener()


# ──────────────────────────────────────────────────────────────────
# FEATURE ENGINEERING
# ──────────────────────────────────────────────────────────────────
def make_default_values() -> Dict[str, float]:
    return {
        "age": 65.0,
        "gender": 0.0,
        "avg_sofa": 6.0,
        "admission_sofa": 5.0,
        "hr_mean": 92.0,
        "hr_std": 12.0,
        "rr_mean": 21.0,
        "rr_std": 4.0,
        "spo2_mean": 96.0,
        "spo2_min": 90.0,
        "nibp_mean": 78.0,
        "abp_measured": 1.0,
        "propofol_total": 400.0,
        "midazolam_total": 10.0,
        "lorazepam_total": 4.0,
        "fentanyl_total": 800.0,
        "unique_sedation_drugs": 2.0,
        "nid_score": 0.35,
    }


def build_row_from_form(form) -> Tuple[pd.DataFrame, Dict[str, float], str]:
    values = make_default_values()
    for key in values.keys():
        try:
            raw = form.get(key, None)
            if raw is not None and raw != "":
                values[key] = float(raw)
        except Exception:
            continue

    gender_str = form.get("gender_select", "Male")
    values["gender"] = 0.0 if gender_str == "Male" else 1.0

    icu_sel = form.get("icu_select", ICU_OPTIONS[0])

    # Build dataframe in FEATURE_NAMES order
    if not FEATURE_NAMES:
        # Fallback: simple order from values + ICU
        cols = list(values.keys())
        row = pd.DataFrame([[values[c] for c in cols]], columns=cols)
    else:
        data = {}
        for col in FEATURE_NAMES:
            if col in values:
                data[col] = values[col]
            elif col.startswith("icu_"):
                # one-hot ICU
                icu_name = col.replace("icu_", "")
                data[col] = 1.0 if icu_name == icu_sel else 0.0
            else:
                data[col] = 0.0
        row = pd.DataFrame([data])

    return row, values, icu_sel


def predict_proba_model(model_name: str, X: pd.DataFrame) -> float:
    model = {
        "xgb": XGB_MODEL,
        "lr": LR_MODEL,
        "ensemble": ENSEMBLE_MODEL,
    }.get(model_name)
    if model is None or not hasattr(model, "predict_proba"):
        return float("nan")
    
    # Raw predict proba
    prob = model.predict_proba(X)[:, 1][0]
    
    # --- CALIBRATION INTERCEPT SHIFT ---
    # XGBoost and Ensemble were trained with scale_pos_weight which artificially inflates 
    # the bias term. We apply a logit intercept shift to counter this and map probabilities 
    # back to true clinical risk percentiles (Centers median ~0.8 back to ~0.5)
    prob_clip = max(0.001, min(0.999, prob))
    log_odds = np.log(prob_clip / (1 - prob_clip))
    
    # Subtracting the empirical bias offset (~1.38 log-odds shift observed in distributions)
    adjusted_log_odds = log_odds - 1.38
    calibrated_prob = 1 / (1 + np.exp(-adjusted_log_odds))
    
    return float(calibrated_prob)

def predict_all_models(X: pd.DataFrame) -> Dict[str, float]:
    """Return probabilities from all three models."""
    return {
        "xgb": predict_proba_model("xgb", X),
        "lr": predict_proba_model("lr", X),
        "ensemble": predict_proba_model("ensemble", X),
    }


def risk_label(prob: float) -> str:
    if not np.isfinite(prob):
        return "UNKNOWN"
    if prob >= 0.65:
        return "HIGH"
    elif prob >= 0.40:
        return "MEDIUM"
    return "LOW"


def compute_shap_dict(X: pd.DataFrame) -> Dict[str, float]:
    if shap is None or XGB_MODEL is None:
        return {}
    try:
        explainer = shap.TreeExplainer(XGB_MODEL)
        vals = explainer.shap_values(X)
        if isinstance(vals, list):
            vals = vals[1][0]
        else:
            vals = vals[0]
            if getattr(vals, "ndim", 1) > 1 and vals.shape[1] == 2:
                vals = vals[:, 1]
        return {feat: float(v) for feat, v in zip(X.columns, vals)}
    except Exception:
        return {}


# ──────────────────────────────────────────────────────────────────
# MQTT DISPATCH — Send alerts to pagers
# ──────────────────────────────────────────────────────────────────
def dispatch_to_pagers(patient_name: str, bed: str, zone: str, risk_pct: str, risk_raw: float, label: str):
    """Publish alert to the correct pager(s) via MQTT."""
    if not MQTT_AVAILABLE:
        return "mqtt_unavailable"
    
    action = "CAM-ICU STAT" if label == "HIGH" else "MONITOR NID"
    
    alert_payload = json.dumps({
        "patient": patient_name,
        "bed": bed,
        "zone": zone,
        "risk": risk_pct,
        "risk_raw": risk_raw,
        "action": action,
        "label": label,
        "timestamp": datetime.now().strftime("%H:%M"),
    })

    dispatched_to = []
    try:
        # Find pagers assigned to this zone
        pagers = get_pagers()
        zone_pagers = [pid for pid, info in pagers.items() if info.get("zone") == zone]
        
        # Send to zone-specific pagers
        for pid in zone_pagers:
            mqtt_publish.single(
                f"deliriumwatch/pager/{pid}/alerts",
                alert_payload,
                hostname=MQTT_BROKER,
                port=MQTT_PORT
            )
            dispatched_to.append(pid)

        print(f">>> ALERT DISPATCHED: {patient_name} [{label}] → {dispatched_to} <<<")
        return ",".join(dispatched_to) if dispatched_to else "No pager in zone"
    except Exception as e:
        print(f"MQTT dispatch error: {e}")
        return "error"


# ──────────────────────────────────────────────────────────────────
# ROUTES
# ──────────────────────────────────────────────────────────────────
@app.route("/", methods=["GET", "POST"])
def index():
    selected_model = "ensemble"
    prob = None
    label = None
    shap_items: List[Tuple[str, float]] = []
    values = make_default_values()
    icu_sel = ICU_OPTIONS[0]
    shap_max = 0.01
    all_probs = {}
    patient_name = ""
    patient_bed = ""
    patient_zone = "Bay A"
    gender_select = "Male"
    dispatch_status = None

    if request.method == "POST":
        selected_model = request.form.get("model_select", "ensemble")
        patient_name = request.form.get("patient_name", "UNKNOWN")
        patient_bed = request.form.get("patient_bed", "N/A")
        patient_zone = request.form.get("patient_zone", "Bay A")
        gender_select = request.form.get("gender_select", "Male")
        
        X_row, values, icu_sel = build_row_from_form(request.form)
        prob = predict_proba_model(selected_model, X_row)
        label = risk_label(prob)
        all_probs = predict_all_models(X_row)

        # Add to ward roster
        patient_entry = {
            "name": patient_name,
            "bed": patient_bed,
            "zone": patient_zone,
            "gender": gender_select,
            "icu": icu_sel,
            "risk_raw": prob,
            "risk_pct": f"{prob*100:.1f}%",
            "label": label,
            "model": selected_model,
            "all_probs": {k: f"{v*100:.1f}" for k, v in all_probs.items() if np.isfinite(v)},
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "values": values,
        }
        add_patient(patient_entry)

        # MQTT pager dispatch for HIGH/MEDIUM
        if label in ("HIGH", "MEDIUM"):
            dispatch_status = dispatch_to_pagers(
                patient_name, patient_bed, patient_zone,
                f"{prob*100:.1f}%", prob, label
            )

        shap_dict = compute_shap_dict(X_row)
        shap_items = sorted(shap_dict.items(), key=lambda kv: abs(kv[1]), reverse=True)[:8]
        shap_max = max((abs(v) for k, v in shap_items), default=0.01)

    return render_template(
        "index.html",
        values=values,
        icu_options=ICU_OPTIONS,
        icu_sel=icu_sel,
        zone_options=ZONE_OPTIONS,
        selected_model=selected_model,
        aurocs=METRICS,
        prob=prob,
        label=label,
        all_probs=all_probs,
        shap_items=shap_items,
        shap_max=shap_max,
        shap_available=bool(shap_items),
        shap_json=json.dumps([{"name": k, "value": v} for k, v in shap_items]) if shap_items else "[]",
        models_loaded={
            "xgb": XGB_MODEL is not None,
            "lr": LR_MODEL is not None,
            "ensemble": ENSEMBLE_MODEL is not None,
        },
        patient_name=patient_name,
        patient_bed=patient_bed,
        patient_zone=patient_zone,
        gender_select=gender_select,
        ward_patients=get_patients(),
        risk_summary=get_risk_summary(),
        pager_fleet=get_pagers(),
        dispatch_status=dispatch_status,
        presets=PRESETS,
    )


@app.route("/api/patients", methods=["GET"])
def api_patients():
    """REST endpoint: return all ward patients as JSON."""
    return jsonify({
        "patients": get_patients(),
        "summary": get_risk_summary(),
    })


@app.route("/api/pagers", methods=["GET"])
def api_pagers():
    """REST endpoint: return pager fleet status."""
    return jsonify(get_pagers())


@app.route("/clear", methods=["POST"])
def clear_ward():
    """Clear all patients from ward roster."""
    clear_patients()
    # Send clear command to all pagers
    if MQTT_AVAILABLE:
        try:
            pagers = get_pagers()
            for pid in pagers:
                mqtt_publish.single(
                    f"deliriumwatch/pager/{pid}/clear",
                    "CLEAR",
                    hostname=MQTT_BROKER,
                    port=MQTT_PORT
                )
        except Exception:
            pass
    return redirect(url_for("index"))


@app.route("/api/presets/<preset_id>", methods=["GET"])
def api_preset(preset_id):
    """Return preset patient data."""
    preset = PRESETS.get(preset_id)
    if preset:
        return jsonify(preset)
    return jsonify({"error": "not found"}), 404


# ──────────────────────────────────────────────────────────────────
# AGENT ROUTES
# ──────────────────────────────────────────────────────────────────
@app.route("/agent", methods=["GET"])
def agent_view():
    return render_template("agent.html", high_risk_indices=high_risk_indices)


@app.route("/api/agent/run", methods=["POST"])
def api_agent_run():
    try:
        body        = request.get_json(force=True) or {}
        patient_idx = body.get("patient_idx")

        if not isinstance(patient_idx, int) or not (0 <= patient_idx <= len(X_test) - 1):
            return jsonify({"error": "invalid index"}), 400

        result = run_delirium_agent(patient_idx, ENSEMBLE_MODEL, X_test, y_test, FEATURE_NAMES)

        if result["risk_result"]["risk_level"] == "HIGH":
            try:
                broker  = os.environ.get("DW_MQTT_BROKER", "172.20.10.2")
                topic   = "deliriumwatch/pager/doc2/alerts"
                payload = json.dumps({
                    "patient_id": patient_idx,
                    "risk":       result["risk_result"]["risk_percentage"],
                    "alert":      result["alert_text"][:120],
                    "timestamp":  datetime.now().isoformat(),
                })
                mqtt_publish.single(topic, payload, hostname=broker)
                print(f"MQTT alert sent for patient {patient_idx}")
            except Exception as mqtt_err:
                print(f"MQTT broker offline, skipping: {mqtt_err}")

        return jsonify(result), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=True)
