import os
from dotenv import load_dotenv
load_dotenv()

import pandas as pd
import shap
from groq import Groq

# ──────────────────────────────────────────────────────────────────
# THRESHOLDS
# ──────────────────────────────────────────────────────────────────
_RISK_LOW    = 0.30
_RISK_MEDIUM = 0.60

_MODIFIABLE_ACTIONS = {
    "nid_score": "Cluster nighttime nursing care — target NID < 0.25 by protecting 22:00–06:00 window",
    "propofol_total": "Reduce propofol dose; consider daily SAT protocol",
    "midazolam_total": "Minimize midazolam — high delirium risk; switch to non-benzo sedation",
    "lorazepam_total": "Taper lorazepam; benzodiazepines independently increase delirium risk",
    "fentanyl_total": "Review opioid burden; consider multimodal analgesia to reduce fentanyl",
    "rr_mean": "Evaluate ventilator settings — elevated RR may signal respiratory distress",
    "spo2_min": "Improve oxygenation; ensure SpO₂ nadir > 92% to reduce hypoxic CNS events",
    "nibp_mean": "Optimise MAP — sustained hypotension (<65 mmHg) increases delirium incidence",
    "unique_sedation_drugs": "Simplify sedation regimen — polypharmacy compounds delirium risk",
}

_NON_MODIFIABLE = {
    "age", "gender", "avg_sofa", "admission_sofa", "abp_measured",
    "hr_mean", "hr_std", "hr_max", "spo2_mean", "rr_std", "abp_mean",
}


# ──────────────────────────────────────────────────────────────────
# FUNCTION 1 — Risk assessment
# ──────────────────────────────────────────────────────────────────
def assess_risk(patient_features: pd.DataFrame, model, feature_names: list) -> dict:
    prob = float(model.predict_proba(patient_features)[:, 1][0])

    if prob < _RISK_LOW:
        level, emoji = "LOW", "🟢"
    elif prob < _RISK_MEDIUM:
        level, emoji = "MEDIUM", "🟡"
    else:
        level, emoji = "HIGH", "🔴"

    return {
        "risk_score": prob,
        "risk_percentage": f"{prob * 100:.1f}%",
        "risk_level": level,
        "risk_emoji": emoji,
    }


# ──────────────────────────────────────────────────────────────────
# FUNCTION 2 — SHAP explanation
# ──────────────────────────────────────────────────────────────────
def explain_patient(
    patient_features: pd.DataFrame,
    model,
    feature_names: list,
    top_n: int = 5,
) -> dict:
    xgb = model.named_estimators_["xgb"]
    explainer = shap.TreeExplainer(xgb)
    shap_values = explainer.shap_values(patient_features)

    # shap_values may be list (binary) or 2-D array
    if isinstance(shap_values, list):
        vals = shap_values[1][0]
    else:
        row = shap_values[0]
        vals = row[:, 1] if row.ndim > 1 and row.shape[-1] == 2 else row

    shap_dict = {feat: float(v) for feat, v in zip(feature_names, vals)}
    sorted_items = sorted(shap_dict.items(), key=lambda kv: kv[1], reverse=True)

    return {
        "top_risk_factors":       [{"feature": f, "value": v} for f, v in sorted_items[:top_n]],
        "top_protective_factors": [{"feature": f, "value": v} for f, v in sorted_items[-top_n:][::-1]],
        "all_shap":               shap_dict,
    }


# ──────────────────────────────────────────────────────────────────
# FUNCTION 3 — Intervention planning
# ──────────────────────────────────────────────────────────────────
def plan_interventions(shap_explanation: dict) -> dict:
    increasing_risk = shap_explanation.get("increasing_risk", [])

    actionable     = []
    non_modifiable = []

    for feat, shap_val in increasing_risk:
        if feat in _MODIFIABLE_ACTIONS:
            actionable.append({
                "feature":     feat,
                "shap_impact": round(shap_val, 4),
                "action":      _MODIFIABLE_ACTIONS[feat],
            })
        elif feat in _NON_MODIFIABLE:
            non_modifiable.append({
                "feature":     feat,
                "shap_impact": round(shap_val, 4),
            })

    return {
        "actionable_interventions": actionable,
        "non_modifiable_risks":     non_modifiable,
        "total_actionable":         len(actionable),
    }


# ──────────────────────────────────────────────────────────────────
# FUNCTION 4 — LLM alert generation
# ──────────────────────────────────────────────────────────────────
def generate_alert(
    risk_result: dict,
    shap_explanation: dict,
    interventions: dict,
    patient_id: str,
) -> str:
    level      = risk_result["risk_level"]
    pct        = risk_result["risk_percentage"]
    emoji      = risk_result["risk_emoji"]
    top_risks  = shap_explanation.get("top_risk_factors", [])
    actions    = interventions.get("actionable_interventions", [])

    top_risk_str   = ", ".join(f"{a['feature']} ({a['value']:+.3f})" for a in top_risks[:3]) or "none identified"
    action_str     = "; ".join(a["action"][:60] for a in actions[:3]) or "standard ICU prophylaxis"

    groq_key = os.environ.get("GROQ_API_KEY", "")
    if groq_key:
        try:
            client = Groq(api_key=groq_key)
            prompt = (
                f"Patient ID: {patient_id}\n"
                f"Delirium risk: {emoji} {level} ({pct})\n"
                f"Top SHAP drivers: {top_risk_str}\n"
                f"Top interventions: {action_str}\n\n"
                "Write a concise clinical alert in exactly 4 sections using these plain-text "
                "headers (all caps, no markdown):\n"
                "RISK SUMMARY\nKEY CONCERNS\nRECOMMENDED ACTIONS\nMONITORING NOTE\n"
                "Maximum 150 words total."
            )
            response = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a clinical decision support system generating brief, "
                            "actionable ICU delirium alerts for nurses and physicians. "
                            "Be direct, factual, and concise."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=250,
            )
            return response.choices[0].message.content.strip()
        except Exception as exc:
            print(f"[generate_alert] Groq failed: {exc}")

    # Fallback — built entirely from structured data
    action_lines = "\n".join(
        f"  • {a['action']}" for a in actions[:3]
    ) or "  • Standard ICU delirium prophylaxis"
    non_mod = interventions.get("non_modifiable_risks", [])
    non_mod_str = ", ".join(r["feature"] for r in non_mod[:3]) or "none"

    return (
        f"RISK SUMMARY\n"
        f"Patient {patient_id}: {emoji} {level} delirium risk ({pct})\n\n"
        f"KEY CONCERNS\n"
        f"Top drivers: {top_risk_str}\n"
        f"Non-modifiable factors: {non_mod_str}\n\n"
        f"RECOMMENDED ACTIONS\n"
        f"{action_lines}\n\n"
        f"MONITORING NOTE\n"
        f"Reassess CAM-ICU every 4 hours. Escalate to attending if risk increases."
    )


# ──────────────────────────────────────────────────────────────────
# FUNCTION 5 — Full pipeline
# ──────────────────────────────────────────────────────────────────
def run_delirium_agent(
    patient_idx: int,
    model,
    X_test: pd.DataFrame,
    y_test,
    feature_names: list,
) -> dict:
    patient_row = X_test.iloc[[patient_idx]]

    # Step 1 — Risk score
    risk_result = assess_risk(patient_row, model, feature_names)

    # Step 2 — SHAP explanation
    shap_explanation = explain_patient(patient_row, model, feature_names)

    # Bridge: expose features with positive SHAP as "increasing_risk"
    shap_explanation["increasing_risk"] = [
        (feat, val)
        for feat, val in shap_explanation["all_shap"].items()
        if val > 0
    ]
    shap_explanation["increasing_risk"].sort(key=lambda kv: kv[1], reverse=True)

    # Step 3 — Interventions
    interventions = plan_interventions(shap_explanation)

    # Step 4 — Alert
    alert_text = generate_alert(
        risk_result,
        shap_explanation,
        interventions,
        patient_id=str(patient_idx),
    )

    actual = int(y_test.iloc[patient_idx]) if hasattr(y_test, "iloc") else int(y_test[patient_idx])

    return {
        "patient_idx":    patient_idx,
        "risk_result":    risk_result,
        "shap_explanation": {
            "top_risk_factors":      shap_explanation["top_risk_factors"],
            "top_protective_factors": shap_explanation["top_protective_factors"],
        },
        "interventions":  interventions,
        "alert_text":     alert_text,
        "actual_label":   actual,
    }
