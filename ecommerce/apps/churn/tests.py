"""
Tests for apps.churn.predictor — the override-rule safety net and the
overall shape of predict_churn()'s return value.

Scope note: these test the PURE LOGIC in predictor.py directly, using
hand-built feature dicts — they don't touch the database or
extract_features(), so they don't need Order/Complaint/Review fixtures.
That keeps them fast and independent of anything else in the app.

A second layer of tests (extract_features() actually pulling correct
numbers from real Order/Complaint/Review rows) is still missing — that
needs DB fixtures for those models and is a good next addition, but is
out of scope here since it depends on exact required fields on those
models that aren't all confirmed yet.
"""
from django.test import TestCase

from apps.churn.predictor import _apply_override_rules, predict_churn


class OverrideRulesTests(TestCase):
    """Direct tests of _apply_override_rules() — no DB, no model file needed
    beyond what's already loaded at import time."""

    def test_no_override_when_model_already_says_high(self):
        """If the model's own score is already >= 0.5, no rule should fire —
        the risk_level and score should pass through unchanged."""
        result = _apply_override_rules(
            feature_dict={'Complain': 1, 'DaySinceLastOrder': 90, 'OrderCount': 1, 'SatisfactionScore': 1},
            proba=0.82,
            risk='high',
        )
        self.assertEqual(result['risk_level'], 'high')
        self.assertEqual(result['score'], 0.82)
        self.assertIsNone(result['override_reason'])

    def test_rule1_complaint_plus_long_gap(self):
        """A real complaint + 30+ days since last order should force high,
        even when the model itself said low."""
        result = _apply_override_rules(
            feature_dict={'Complain': 1, 'DaySinceLastOrder': 45, 'OrderCount': 10, 'SatisfactionScore': 4},
            proba=0.10,
            risk='low',
        )
        self.assertEqual(result['risk_level'], 'high')
        self.assertGreaterEqual(result['score'], 0.5)
        self.assertIn('complaint', result['override_reason'].lower())

    def test_rule2_inactive_with_thin_history(self):
        """45+ day gap with 3 or fewer orders should force high."""
        result = _apply_override_rules(
            feature_dict={'Complain': 0, 'DaySinceLastOrder': 61, 'OrderCount': 3, 'SatisfactionScore': 4},
            proba=0.03,
            risk='low',
        )
        self.assertEqual(result['risk_level'], 'high')
        self.assertGreaterEqual(result['score'], 0.5)
        self.assertIn('inactive', result['override_reason'].lower())

    def test_rule3_complaint_plus_low_satisfaction(self):
        """A complaint stacked with a satisfaction score of 2 or below
        should force high, independent of order recency."""
        result = _apply_override_rules(
            feature_dict={'Complain': 1, 'DaySinceLastOrder': 2, 'OrderCount': 20, 'SatisfactionScore': 1},
            proba=0.05,
            risk='low',
        )
        self.assertEqual(result['risk_level'], 'high')
        self.assertGreaterEqual(result['score'], 0.5)

    def test_genuinely_safe_customer_stays_low(self):
        """An active, complaint-free, satisfied customer should NOT be
        caught by any override rule — this is the case we manually
        verified earlier with test_loyal_customer."""
        result = _apply_override_rules(
            feature_dict={'Complain': 0, 'DaySinceLastOrder': 0, 'OrderCount': 6, 'SatisfactionScore': 5},
            proba=0.12,
            risk='low',
        )
        self.assertEqual(result['risk_level'], 'low')
        self.assertEqual(result['score'], 0.12)
        self.assertIsNone(result['override_reason'])

    def test_overridden_score_never_below_half(self):
        """Whenever an override forces risk_level to 'high', the score must
        also be >= 0.5 — this is the exact badge/score mismatch bug we
        fixed, and it should never regress."""
        result = _apply_override_rules(
            feature_dict={'Complain': 0, 'DaySinceLastOrder': 90, 'OrderCount': 1, 'SatisfactionScore': 3},
            proba=0.01,
            risk='low',
        )
        self.assertEqual(result['risk_level'], 'high')
        self.assertGreaterEqual(result['score'], 0.5)


class PredictChurnShapeTests(TestCase):
    """Tests that predict_churn() always returns a well-formed result,
    using a complete, realistic feature dict (as extract_features()
    would produce)."""

    def _sample_features(self, **overrides):
        base = {
            'Gender': 'Male',
            'MaritalStatus': 'Single',
            'Tenure': 3,
            'HourSpendOnApp': 0.5,
            'SatisfactionScore': 4,
            'NumberOfAddress': 1,
            'Complain': 0,
            'CouponUsed': 1,
            'OrderCount': 5,
            'DaySinceLastOrder': 5,
            'CashbackAmount': 50.0,
        }
        base.update(overrides)
        return base

    def test_returns_all_expected_keys(self):
        result = predict_churn(self._sample_features())
        for key in ('score', 'risk_level', 'will_churn', 'model_score',
                    'model_risk_level', 'override_reason', 'debug'):
            self.assertIn(key, result)

    def test_risk_level_is_always_valid(self):
        result = predict_churn(self._sample_features())
        self.assertIn(result['risk_level'], ('low', 'high'))

    def test_score_and_risk_level_never_disagree(self):
        """The core consistency guarantee: risk_level == 'high' if and
        only if score >= 0.5, for any input — model-driven or overridden."""
        cases = [
            self._sample_features(),  # a normal, unremarkable customer
            self._sample_features(Complain=1, DaySinceLastOrder=60, OrderCount=2),  # should override
            self._sample_features(SatisfactionScore=5, DaySinceLastOrder=0, OrderCount=10),  # clearly safe
        ]
        for features in cases:
            result = predict_churn(features)
            if result['risk_level'] == 'high':
                self.assertGreaterEqual(result['score'], 0.5)
            else:
                self.assertLess(result['score'], 0.5)

    def test_will_churn_matches_risk_level(self):
        result = predict_churn(self._sample_features())
        self.assertEqual(result['will_churn'], result['risk_level'] == 'high')