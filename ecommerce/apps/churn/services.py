from django.contrib.auth import get_user_model

from apps.churn.models import ChurnScore
from apps.churn.features import extract_features
from apps.churn.predictor import predict_churn

User = get_user_model()


def score_all_customers(debug=False, log=None):
    """
    Scores every active, non-staff customer for churn risk and saves
    a new ChurnScore row for each.

    This is the single source of truth for "how do we score everyone" —
    both the manual `score_customers` management command and the
    automatic Celery Beat task call this function, so the two entry
    points can never drift apart or behave differently.

    `log`: an optional callable that receives progress lines as strings.
    Pass `self.stdout.write` from a management command, or a logger's
    `.info` method from a Celery task. If omitted, nothing is printed —
    useful for silent/background calls.

    Returns a dict summary: {'total', 'high', 'low', 'errors'}.
    """
    def _log(msg):
        if log:
            log(msg)

    users = User.objects.filter(
        is_staff=False,
        is_superuser=False,
        is_active=True,
    )

    _log(f'Scoring {users.count()} customers...\n')
    high = low = errors = 0

    for user in users:
        try:
            features = extract_features(user)
            result = predict_churn(features)

            # Using create() (not update_or_create) keeps a full score
            # history per customer rather than overwriting the one
            # existing row — the dashboard's "latest per customer"
            # query and the score-history chart both depend on this.
            ChurnScore.objects.create(
                customer=user,
                score=result['score'],
                risk_level=result['risk_level'],
                override_reason=result.get('override_reason'),
            )

            if result['risk_level'] == 'high':
                high += 1
            else:
                low += 1

            _log(
                f"  {user.username:<20} "
                f"{result['risk_level']:<8} "
                f"score={result['score']}"
            )

            if debug:
                _log("    Raw inputs:")
                for k, v in features.items():
                    _log(f"      {k}: {v}")
                _log("    Computed feature row (model input order):")
                for k, v in result['debug'].items():
                    _log(f"      {k}: {v}")
                if result.get('override_reason'):
                    _log(f"    \u26a0 Override: {result['override_reason']}")
                _log("")

        except Exception as e:
            errors += 1
            _log(f"  ERROR for {user.username}: {e}")

    _log(f"\n\u2705 Done! High:{high}  Low:{low}  Errors:{errors}")

    return {
        'total': users.count(),
        'high': high,
        'low': low,
        'errors': errors,
    }