import joblib
lr = joblib.load('lr_model.pkl')
print("LR type:", type(lr))
xgb = joblib.load('xgb_model.pkl')
print("XGB type:", type(xgb))
