import joblib
import pandas as pd
import numpy as np

xgb = joblib.load('xgb_model.pkl')
feats = joblib.load('feature_names.pkl')

np.random.seed(42)
n = 1000
data = {}
for f in feats:
    if "age" in f: data[f] = np.random.normal(65, 15, n)
    elif "sofa" in f: data[f] = np.clip(np.random.normal(5, 3, n), 0, None)
    elif "hr_mean" in f: data[f] = np.random.normal(85, 15, n)
    elif "nid_score" in f: data[f] = np.clip(np.random.normal(0.35, 0.1, n), 0, 1)
    elif f.startswith("icu_"): data[f] = np.random.choice([0, 1], n)
    else: data[f] = np.random.normal(10, 5, n)

X_dummy = pd.DataFrame(data)[feats]

probs = xgb.predict_proba(X_dummy)[:, 1]
print("Min prob:", probs.min())
print("Max prob:", probs.max())
print("Mean prob:", probs.mean())
print("Median prob:", np.median(probs))
print("10th percentile:", np.percentile(probs, 10))
print("25th percentile:", np.percentile(probs, 25))
print("75th percentile:", np.percentile(probs, 75))
print("90th percentile:", np.percentile(probs, 90))

