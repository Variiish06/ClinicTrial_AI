import joblib
import pandas as pd
app_defaults = {
    "age": 65.0, "gender": 0.0, "avg_sofa": 6.0, "admission_sofa": 5.0,
    "hr_mean": 92.0, "hr_std": 12.0, "rr_mean": 21.0, "rr_std": 4.0,
    "spo2_mean": 96.0, "spo2_min": 90.0, "nibp_mean": 78.0, "abp_measured": 1.0,
    "propofol_total": 400.0, "midazolam_total": 10.0, "lorazepam_total": 4.0,
    "fentanyl_total": 800.0, "unique_sedation_drugs": 2.0, "nid_score": 0.35
}
feats = joblib.load('feature_names.pkl')
data = {}
for col in feats:
    if col in app_defaults:
        data[col] = app_defaults[col]
    elif col == "icu_Medical Intensive Care Unit (MICU)":
        data[col] = 1.0
    else:
        data[col] = 0.0

X = pd.DataFrame([data])
xgb = joblib.load('xgb_model.pkl')
lr = joblib.load('lr_model.pkl')
ensemble = joblib.load('deliriumwatch_ensemble.pkl')

print("XGB:", xgb.predict_proba(X)[:, 1][0])
print("LR:", lr.predict_proba(X)[:, 1][0])
print("Ensemble:", ensemble.predict_proba(X)[:, 1][0])

X_low = X.copy()
X_low["age"] = 30.0
X_low["avg_sofa"] = 2.0
X_low["nid_score"] = 0.1
X_low["propofol_total"] = 0
X_low["fentanyl_total"] = 0

print("XGB Low Risk:", xgb.predict_proba(X_low)[:, 1][0])
print("LR Low Risk:", lr.predict_proba(X_low)[:, 1][0])
print("Ensemble Low Risk:", ensemble.predict_proba(X_low)[:, 1][0])

