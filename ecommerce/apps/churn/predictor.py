import os
import joblib
import pandas as pd
from django.conf import settings

_MODEL_DIR = os.path.join(settings.BASE_DIR, 'apps', 'churn', 'ml_models')
_model          = joblib.load(os.path.join(_MODEL_DIR, 'churn_model.pkl'))
_columns        = joblib.load(os.path.join(_MODEL_DIR, 'feature_columns.pkl'))
_encoding_maps  = joblib.load(os.path.join(_MODEL_DIR, 'encoding_maps.pkl'))


def predict_churn(feature_dict: dict) -> dict:
    """
    Args:
        feature_dict: output of features.extract_features(user)
                      categorical columns must be RAW TEXT e.g. 'Male', not 1
    Returns:
        { 'score': float, 'risk_level': str, 'will_churn': bool }
    """
    enc = feature_dict.copy()

    # Step 1: encode text → number using training maps
    for col, mapping in _encoding_maps.items():
        if col in enc:
            enc[col] = mapping.get(enc[col], 0)

    # Step 2: compute the 9 engineered features (must match training exactly)
    tenure     = enc.get('Tenure', 0) or 0
    order_cnt  = enc.get('OrderCount', 0) or 0
    cashback   = enc.get('CashbackAmount', 0) or 0
    coupons    = enc.get('CouponUsed', 0) or 0
    app_hours  = enc.get('HourSpendOnApp', 0) or 0
    devices    = enc.get('NumberOfDeviceRegistered', 0) or 0
    last_order = enc.get('DaySinceLastOrder', 0) or 0
    sat_score  = enc.get('SatisfactionScore', 3) or 3
    complain   = enc.get('Complain', 0) or 0

    enc['recency_risk']       = int(last_order > 10)
    enc['order_rate']         = order_cnt / (tenure + 1)
    enc['low_order_flag']     = int(order_cnt <= 2)
    enc['cashback_per_month'] = cashback / (tenure + 1)
    enc['coupon_usage_rate']  = coupons / (order_cnt + 1)
    enc['low_engagement']     = int(app_hours < 2)
    enc['engagement_score']   = (app_hours * 0.3 + order_cnt * 0.4 +
                                  devices * 0.15 + coupons * 0.15)
    enc['dissatisfied']       = int(sat_score <= 2 or complain == 1)
    enc['churn_risk_score']   = (enc['recency_risk']   * 0.30 +
                                  enc['low_order_flag'] * 0.25 +
                                  enc['low_engagement'] * 0.25 +
                                  enc['dissatisfied']   * 0.20)

    # Step 3: build DataFrame in exact column order model expects
    row   = {col: enc.get(col, 0) for col in _columns}
    df    = pd.DataFrame([row])[_columns]
    proba = float(_model.predict_proba(df)[0][1])

    if proba >= 0.5:
        risk = 'high'
    else:
        risk = 'low'

    return {
        'score':      round(proba, 3),
        'risk_level': risk,
        'will_churn': proba >= 0.5,
    }