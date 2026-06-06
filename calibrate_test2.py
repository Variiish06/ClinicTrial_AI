import numpy as np

def calibrate(p):
    p = np.clip(p, 0.001, 0.999)
    log_odds = np.log(p / (1 - p))
    # Remove the artificial offset introduced by the scale_pos_weight
    # Adjust this factor based on median tuning
    adjusted_log_odds = log_odds - 1.25 
    p_calib = 1 / (1 + np.exp(-adjusted_log_odds))
    return p_calib

print("0.95 ->", calibrate(0.95))
print("0.80 ->", calibrate(0.80))
print("0.60 ->", calibrate(0.60))
print("0.40 ->", calibrate(0.40))
