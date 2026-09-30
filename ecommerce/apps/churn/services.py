from django.contrib.auth import get_user_model

from apps.churn.models import ChurnScore
from apps.churn.features import extract_features
from apps.churn.predictor import predict_churn
from apps.churn.retention import trigger_winback, expire_retention_campaigns

User = get_user_model()


def score_customer(user, debug=False, log=None, allow_winback=True):
    """
    Scores ONE customer and saves a new ChurnScore row for them.

    This is the single place where "how do we score a customer" lives.
    score_all_customers() calls it for every customer, and the
    complaints app calls it for one customer the moment a complaint
    changes status, so a resolved complaint is reflected right away
    instead of waiting for the next scheduled run.

    Returns a dict: {'result': <predict_churn output>,
                     'winback_coupon': <Coupon or None>}.
    Raises on failure — callers decide how to handle errors.
    """
    def _log(msg):
        if log:
            log(msg)

    features = extract_features(user)
    result = predict_churn(features)

    # Look at this customer's most recent PREVIOUS score, before
    # we save the new one — this is how we know whether they're
    # newly at risk (worth acting on) or have been high-risk for
    # a while already (already acted on, don't repeat it daily).
    previous = ChurnScore.objects.filter(customer=user).order_by('-predicted_at').first()

    # Using create() (not update_or_create) keeps a full score
    # history per customer rather than overwriting the one
    # existing row — the dashboard's "latest per customer"
    # query and the score-history chart both depend on this.
    score_row = ChurnScore.objects.create(
        customer=user,
        score=result['score'],
        risk_level=result['risk_level'],
        override_reason=result.get('override_reason'),
        features=features,
        model_score=result['model_score'],
        top_factors={
            'raising':  result.get('top_factors'),
            'lowering': result.get('protective_factors'),
        },
    )

    coupon = None
    if allow_winback and result['risk_level'] == 'high':
        # Only trigger a win-back offer the MOMENT someone crosses
        # into high risk — not every single day they remain high,
        # or they'd get a new coupon every day forever.
        just_became_high = (
            previous is None or previous.risk_level != 'high'
        )
        if just_became_high:
            coupon = trigger_winback(user, source_score=score_row)
            if coupon:
                _log(f"    \U0001F381 Win-back coupon sent: {coupon.code}")

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
        if result.get('top_factors'):
            _log("    Top factors pushing toward churn (SHAP):")
            for tf in result['top_factors']:
                _log(f"      {tf['feature']} = {tf['value']} (impact: +{tf['impact']})")
        _log("")

    return {'result': result, 'winback_coupon': coupon}


def score_all_customers(debug=False, log=None):
    """
    Scores every active, non-staff customer for churn risk and saves
    a new ChurnScore row for each.

    This is the single source of truth for "how do we score everyone" —
    both the manual `score_customers` management command and the
    automatic Celery Beat task call this function, so the two entry
    points can never drift apart or behave differently. Each customer
    is scored by score_customer(), the same function used for
    one-off re-scoring.

    `log`: an optional callable that receives progress lines as strings.
    Pass `self.stdout.write` from a management command, or a logger's
    `.info` method from a Celery task. If omitted, nothing is printed —
    useful for silent/background calls.

    Returns a dict summary: {'total', 'high', 'low', 'errors'}.
    """
    def _log(msg):
        if log:
            log(msg)

    # Keep campaign statuses current as part of the same daily workflow.
    expire_retention_campaigns()

    users = User.objects.filter(
        is_staff=False,
        is_superuser=False,
        is_active=True,
    )

    _log(f'Scoring {users.count()} customers...\n')
    high = low = errors = winbacks_sent = 0

    for user in users:
        try:
            outcome = score_customer(user, debug=debug, log=log)

            if outcome['result']['risk_level'] == 'high':
                high += 1
            else:
                low += 1

            if outcome['winback_coupon']:
                winbacks_sent += 1

        except Exception as e:
            errors += 1
            _log(f"  ERROR for {user.username}: {e}")

    _log(f"\n\u2705 Done! High:{high}  Low:{low}  Errors:{errors}  Win-backs sent:{winbacks_sent}")

    return {
        'total': users.count(),
        'high': high,
        'low': low,
        'errors': errors,
        'winbacks_sent': winbacks_sent,
    }