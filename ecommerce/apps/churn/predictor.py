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


def _apply_override_rules(feature_dict: dict, proba: float, risk: str) -> dict:
    """
    Business-rule safety net on top of the model's raw prediction.

    Why this exists: the training dataset (Kaggle E-Commerce Dataset)
    has a few counterintuitive correlations that our own EDA flagged —
    DaySinceLastOrder correlates NEGATIVELY with churn (-0.16), and
    churners in the source data actually reported HIGHER satisfaction
    scores than non-churners. So the model can under-flag a customer
    who has a real complaint on file and hasn't ordered in a long time,
    because it learned the opposite pattern from the training data.

    When a rule fires, it bumps BOTH the risk_level AND the displayed
    score above the 0.5 line — never just the label. A dashboard
    showing "High" next to a 0.08 looks like a bug even when the
    underlying logic is intentional, so the score always has to agree
    with the badge next to it. The raw model probability is preserved
    separately as 'model_score' for anyone who wants to see what the
    model itself actually thought.

    Thresholds (30 / 45 days) and the bumped score (0.65) are starting
    points based on our own test data — revisit once we have more real
    customer history.
    """
    OVERRIDE_SCORE = 0.65  # displayed score when a rule forces 'high'

    if risk == 'high':
        return {'risk_level': risk, 'score': proba, 'override_reason': None}

    complain           = feature_dict.get('Complain', 0)
    satisfaction       = feature_dict.get('SatisfactionScore', 3)
    days_since_order    = feature_dict.get('DaySinceLastOrder', 0)
    order_count        = feature_dict.get('OrderCount', 0)

    # Rule 1: recent complaint + gone quiet for a month+
    if complain == 1 and days_since_order > 30:
        return {
            'risk_level': 'high',
            'score': max(proba, OVERRIDE_SCORE),
            'override_reason': 'Open complaint + no order in 30+ days',
        }

    # Rule 2: long inactivity on an account that never built up much history
    if days_since_order > 45 and order_count <= 3:
        return {
            'risk_level': 'high',
            'score': max(proba, OVERRIDE_SCORE),
            'override_reason': 'Inactive 45+ days with a thin order history',
        }

    # Rule 3: complaint stacked with a low satisfaction rating
    if complain == 1 and satisfaction <= 2:
        return {
            'risk_level': 'high',
            'score': max(proba, OVERRIDE_SCORE),
            'override_reason': 'Open complaint + low satisfaction rating',
        }

    return {'risk_level': risk, 'score': proba, 'override_reason': None}


def predict_churn(feature_dict: dict) -> dict:
    """
    Takes the 11 raw features from extract_features(), encodes the
    2 categoricals (Gender, MaritalStatus), then predicts using the
    tuned XGBoost model trained on exactly these 11 columns.

    No feature engineering — the 11-feature model was trained on raw
    features only (no recency_risk, order_rate, etc.).

    After the model's raw prediction, a small set of business-rule
    overrides (see _apply_override_rules) can bump a 'low' verdict up
    to 'high' for known model blind spots. When that happens, the
    DISPLAYED score is also raised to match — 'score' (what gets shown
    and saved to ChurnScore) always agrees with 'risk_level'. The raw,
    un-bumped model probability is kept separately as 'model_score' so
    it's never lost, just not shown as the headline number.
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

    model_risk = 'high' if proba >= 0.5 else 'low'

    override = _apply_override_rules(feature_dict, proba, model_risk)

    return {
        'score':            round(override['score'], 3),
        'risk_level':       override['risk_level'],
        'will_churn':       override['risk_level'] == 'high',
        'model_score':      proba,          # raw model output, never adjusted
        'model_risk_level': model_risk,     # what the model alone would say
        'override_reason':  override['override_reason'],
        'debug':            {k: enc.get(k) for k in _columns},
    }