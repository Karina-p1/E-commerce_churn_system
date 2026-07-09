import os
import joblib
import pandas as pd
from django.conf import settings

_MODEL_DIR      = os.path.join(settings.BASE_DIR, 'apps', 'churn', 'ml_models')
_model          = joblib.load(os.path.join(_MODEL_DIR, 'churn_model.pkl'))
_columns        = joblib.load(os.path.join(_MODEL_DIR, 'feature_columns.pkl'))
_encoding_maps  = joblib.load(os.path.join(_MODEL_DIR, 'encoding_maps.pkl'))

# Confirm at startup that the loaded model matches the 11-feature schema
assert len(_columns) == 11, (
    f"Expected 11 feature columns, got {len(_columns)}. "
    "Re-run score_customers after replacing the model artifacts."
)


def predict_churn(feature_dict: dict) -> dict:
    """
    Takes the 11 raw features from extract_features(), encodes the
    2 categoricals (Gender, MaritalStatus), then predicts using the
    tuned XGBoost model trained on exactly these 11 columns.

    No feature engineering — the 11-feature model was trained on raw
    features only (no recency_risk, order_rate, etc.).
    """
    enc = feature_dict.copy()

    # Step 1: encode Gender and MaritalStatus → numeric
    for col, mapping in _encoding_maps.items():
        if col in enc:
            enc[f'{col}_encoded'] = mapping.get(enc[col], 0)

    # Step 2: build DataFrame in the exact 11-column order the model expects
    row   = {col: enc.get(col, 0) for col in _columns}
    df    = pd.DataFrame([row])[_columns]
    proba = float(_model.predict_proba(df)[0][1])
    proba = round(proba, 3)

    risk = 'high' if proba >= 0.5 else 'low'

    return {
        'score':      proba,
        'risk_level': risk,
        'will_churn': proba >= 0.5,
        'debug':      {k: enc.get(k) for k in _columns},
    }