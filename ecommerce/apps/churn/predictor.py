import os
import joblib
import pandas as pd
from django.conf import settings


# Load once when Django starts — not on every prediction call
_MODEL_DIR   = os.path.join(settings.BASE_DIR, 'ml_models')
_model       = joblib.load(os.path.join(_MODEL_DIR, 'churn_model.pkl'))
_columns     = joblib.load(os.path.join(_MODEL_DIR, 'feature_columns.pkl'))


def predict_churn(feature_dict: dict) -> dict:
    """
    Args:
        feature_dict: output of features.extract_features(user)
    Returns:
        { 'score': float, 'risk_level': str, 'will_churn': bool }
    """
    df    = pd.DataFrame([feature_dict])[_columns]
    proba = _model.predict_proba(df)[0][1]

    if proba >= 0.7:
        risk = 'high'
    elif proba >= 0.4:
        risk = 'medium'
    else:
        risk = 'low'

    return {
        'score':      round(float(proba), 3),
        'risk_level': risk,
        'will_churn': proba >= 0.5,
    }