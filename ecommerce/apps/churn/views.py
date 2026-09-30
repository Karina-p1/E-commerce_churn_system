import csv

from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth import get_user_model
from django.db.models import Avg, OuterRef, Subquery, Count, Q, Sum
from django.utils import timezone

from .models import ChurnScore, RetentionCampaign
from .features import extract_features, extract_features_with_metadata
from .predictor import predict_churn
from .services import score_all_customers
from apps.complaints.models import Complaint

User = get_user_model()


def is_admin(user):
    return user.is_staff or user.is_superuser


def _latest_scores_queryset():
    """
    Shared helper: one row per customer, their most recent ChurnScore only.
    Used by the dashboard, the CSV export, and the summary counts so all
    three always agree with each other.
    """
    latest_ids = (
        ChurnScore.objects
        .filter(customer=OuterRef('customer'))
        .order_by('-predicted_at')
        .values('id')[:1]
    )
    return ChurnScore.objects.filter(id__in=Subquery(latest_ids))


@login_required
@user_passes_test(is_admin)
def churn_dashboard(request):

    # order_total excludes cancelled orders, matching exactly what
    # features.py feeds the model (so the dashboard and the model agree).
    scores = (
        _latest_scores_queryset()
        .select_related('customer')
        .annotate(order_total=Count(
            'customer__orders',
            filter=~Q(customer__orders__status='cancelled'),
        ))
        .order_by('-score')
    )

    # Filter by risk level if requested
    risk_filter = request.GET.get('risk', 'all')
    if risk_filter in ('high', 'low'):
        scores = scores.filter(risk_level=risk_filter)

    # Summary counts — always from the full unfiltered latest-score set
    all_scores = _latest_scores_queryset()

    total      = all_scores.count()
    high_count = all_scores.filter(risk_level='high').count()
    low_count  = all_scores.filter(risk_level='low').count()
    avg_score  = all_scores.aggregate(a=Avg('score'))['a'] or 0

    context = {
        'scores':      scores,
        'risk_filter': risk_filter,
        'total':       total,
        'high_count':  high_count,
        'low_count':   low_count,
        'avg_score':   round(avg_score * 100, 1),
    }
    return render(request, 'churn/dashboard.html', context)


@login_required
@user_passes_test(is_admin)
def refresh_scores(request):
    """
    The dashboard's "Refresh scores" button. Runs the EXACT same
    score_all_customers() function as `python manage.py score_customers`
    and the nightly Celery task — so clicking this button is now
    genuinely identical to running the command by hand, not just a
    page reload showing stale data.

    Runs synchronously (no Celery queue) so the new scores are already
    saved by the time the redirect happens and the dashboard re-renders
    — with only a handful of customers this completes in well under a
    second. If your customer base grows large enough that this starts
    feeling slow in the browser, that's the point to switch this to
    queue score_all_customers_task.delay() instead and show a
    "scoring in progress" state rather than blocking the request.
    """
    if request.method != 'POST':
        return redirect('churn:dashboard')

    summary = score_all_customers(debug=False, log=None)

    messages.success(
        request,
        f"Scores refreshed — {summary['total']} customers scored "
        f"({summary['high']} high risk, {summary['low']} low risk)."
    )

    return redirect('churn:dashboard')


@login_required
@user_passes_test(is_admin)
def churn_customer_detail(request, customer_id):
    """
    Drill-down page for a single customer: their full current feature
    breakdown (recomputed live, so it's always up to date even if they've
    acted since the last score_customers run) plus their score history
    for the trend chart.
    """
    customer = get_object_or_404(User, id=customer_id, is_staff=False, is_superuser=False)

    try:
        features, feature_input_notes = extract_features_with_metadata(customer)
        result = predict_churn(features)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect('churn:dashboard')

    history = (
        ChurnScore.objects
        .filter(customer=customer)
        .order_by('predicted_at')
    )

    # (x = epoch milliseconds) lets Chart.js draw a true time axis, so
    # gaps between runs look like gaps instead of being evenly spaced.
    history_points = [
        {
            'x': int(h.predicted_at.timestamp() * 1000),
            'y': h.score,
            'reason': h.override_reason or '',
        }
        for h in history
    ]

    latest_saved = history.last()

    retention_campaigns = (
        RetentionCampaign.objects
        .filter(customer=customer)
        .select_related(
            'coupon',
            'notification',
            'recovered_order',
            'source_score',
        )
        .prefetch_related('recovered_order__items')
        .order_by('-sent_at')
    )

    # Compare the freshly computed live score with the latest saved score.
    # These values are prepared here so the template stays simple and does
    # not need to perform arithmetic.
    score_changed = False
    score_delta = 0
    score_delta_abs = 0
    score_direction = 'same'

    if latest_saved is not None:
        score_delta = round(result['score'] - latest_saved.score, 2)
        score_delta_abs = abs(score_delta)
        score_changed = score_delta != 0

        if score_delta > 0:
            score_direction = 'increased'
        elif score_delta < 0:
            score_direction = 'decreased'

    # _factors() already returns strongest factors first, so index 0 is
    # the main risk driver / main protective factor when one exists.
    main_risk_driver = result.get('top_factors', [])[0] if result.get('top_factors') else None
    main_protective_factor = (
        result.get('protective_factors', [])[0]
        if result.get('protective_factors')
        else None
    )

    context = {
        'customer':                customer,
        'features':                features,
        'result':                  result,
        'history':                 history,
        'history_points':          history_points,
        'latest_saved':            latest_saved,
        'feature_input_notes':     feature_input_notes,
        'retention_campaigns':      retention_campaigns,
        'score_changed':           score_changed,
        'score_delta':             score_delta,
        'score_delta_abs':         score_delta_abs,
        'score_direction':         score_direction,
        'main_risk_driver':        main_risk_driver,
        'main_protective_factor':  main_protective_factor,
    }
    return render(request, 'churn/customer_detail.html', context)



@login_required
@user_passes_test(is_admin)
def retention_dashboard(request):
    """
    Admin view for the full retention funnel:

    campaign sent -> notification viewed -> coupon used -> customer returned
    -> model re-score -> risk outcome.
    """
    from .retention import expire_retention_campaigns

    # Keep the page truthful even if the daily Celery scoring task has not
    # run yet today.
    expire_retention_campaigns()

    status_filter = request.GET.get('status', 'all')

    campaigns = (
        RetentionCampaign.objects
        .select_related(
            'customer',
            'coupon',
            'notification',
            'source_score',
            'recovered_order',
        )
        .prefetch_related('recovered_order__items')
        .order_by('-sent_at')
    )

    valid_statuses = {'SENT', 'VIEWED', 'RECOVERED', 'EXPIRED'}
    if status_filter in valid_statuses:
        campaigns = campaigns.filter(status=status_filter)

    all_campaigns = RetentionCampaign.objects.all()

    total_campaigns = all_campaigns.count()
    viewed_count = all_campaigns.filter(viewed_at__isnull=False).count()
    redeemed_count = all_campaigns.filter(
        used_campaign_coupon=True
    ).count()
    recovered_count = all_campaigns.filter(
        recovered_order__isnull=False
    ).count()
    risk_reduced_count = all_campaigns.filter(
        outcome='RISK_REDUCED'
    ).count()

    recovered_revenue = (
        all_campaigns.aggregate(total=Sum('recovered_revenue'))['total']
        or 0
    )

    coupon_revenue = (
        all_campaigns
        .filter(used_campaign_coupon=True)
        .aggregate(total=Sum('recovered_revenue'))['total']
        or 0
    )

    recovery_rate = round(
        (recovered_count / total_campaigns) * 100,
        1
    ) if total_campaigns else 0

    redemption_rate = round(
        (redeemed_count / total_campaigns) * 100,
        1
    ) if total_campaigns else 0

    viewed_rate = round(
        (viewed_count / total_campaigns) * 100,
        1
    ) if total_campaigns else 0

    return render(request, 'churn/retention_dashboard.html', {
        'campaigns': campaigns,
        'status_filter': status_filter,
        'total_campaigns': total_campaigns,
        'viewed_count': viewed_count,
        'viewed_rate': viewed_rate,
        'redeemed_count': redeemed_count,
        'recovered_count': recovered_count,
        'risk_reduced_count': risk_reduced_count,
        'recovered_revenue': recovered_revenue,
        'coupon_revenue': coupon_revenue,
        'recovery_rate': recovery_rate,
        'redemption_rate': redemption_rate,
    })


# Human-facing labels for the 11 raw churn features.
_RETENTION_FEATURE_LABELS = {
    'Complain': 'Complaint status',
    'DaySinceLastOrder': 'Days since last order',
    'OrderCount': 'Order count',
    'CouponUsed': 'Coupons used',
    'SatisfactionScore': 'Satisfaction score',
    'HourSpendOnApp': 'Average app time',
    'NumberOfAddress': 'Saved addresses',
    'CashbackAmount': 'Coupon savings',
    'Tenure': 'Tenure',
    'Gender': 'Gender',
    'MaritalStatus': 'Marital status',
}


def _retention_feature_changes(before_features, current_features):
    """
    Compare the campaign-start feature snapshot with the latest saved
    churn-score snapshot.

    This explains what changed in the CUSTOMER DATA. It does not claim
    that any one change caused the score movement.
    """
    before_features = before_features or {}
    current_features = current_features or {}

    preferred_order = [
        'Complain',
        'DaySinceLastOrder',
        'OrderCount',
        'CouponUsed',
        'SatisfactionScore',
        'HourSpendOnApp',
        'NumberOfAddress',
        'CashbackAmount',
        'Tenure',
        'Gender',
        'MaritalStatus',
    ]

    changes = []

    for feature in preferred_order:
        if feature not in before_features or feature not in current_features:
            continue

        old = before_features.get(feature)
        new = current_features.get(feature)

        if old == new:
            continue

        title = f"{_RETENTION_FEATURE_LABELS.get(feature, feature)} changed"
        explanation = "Customer data changed after the intervention."

        if feature == 'Complain' and old == 1 and new == 0:
            title = "Active complaint cleared"
            explanation = (
                "The churn input changed from an active complaint to no active complaint."
            )
        elif feature == 'DaySinceLastOrder':
            if isinstance(old, (int, float)) and isinstance(new, (int, float)) and new < old:
                title = "Customer returned more recently"
                explanation = "Days since the last order decreased."
        elif feature == 'OrderCount':
            if isinstance(old, (int, float)) and isinstance(new, (int, float)) and new > old:
                title = "Order history increased"
                explanation = "The customer placed additional non-cancelled order(s)."
        elif feature == 'CouponUsed':
            if isinstance(old, (int, float)) and isinstance(new, (int, float)) and new > old:
                title = "Coupon usage increased"
                explanation = "The number of orders using a coupon increased."
        elif feature == 'SatisfactionScore':
            explanation = "The customer's review-based satisfaction input changed."
        elif feature == 'HourSpendOnApp':
            explanation = "Average recent app activity changed."

        changes.append({
            'feature': feature,
            'label': _RETENTION_FEATURE_LABELS.get(feature, feature),
            'before': old,
            'after': new,
            'title': title,
            'explanation': explanation,
        })

    return changes


def _retention_campaign_timeline(campaign, resolved_complaints, latest_score):
    """
    Build a truthful chronological timeline from persisted timestamps.
    """
    events = []

    source_score = campaign.source_score
    if source_score:
        events.append({
            'at': source_score.predicted_at,
            'type': 'risk',
            'title': 'High risk detected',
            'detail': (
                f"Saved churn score {source_score.score:.2f} "
                f"({source_score.risk_level.title()} risk)."
            ),
        })

    events.append({
        'at': campaign.sent_at,
        'type': 'campaign',
        'title': 'Win-back campaign sent',
        'detail': (
            f"Coupon {campaign.coupon.code} created for this customer."
            if campaign.coupon
            else "Targeted retention campaign created."
        ),
    })

    if campaign.viewed_at:
        events.append({
            'at': campaign.viewed_at,
            'type': 'viewed',
            'title': 'Notification viewed',
            'detail': 'The customer opened/read the retention notification.',
        })

    if campaign.redeemed_at and campaign.used_campaign_coupon:
        events.append({
            'at': campaign.redeemed_at,
            'type': 'coupon',
            'title': 'Win-back coupon redeemed',
            'detail': (
                f"{campaign.coupon.code} was used on the return purchase."
                if campaign.coupon
                else "The campaign coupon was used on the return purchase."
            ),
        })

    if campaign.returned_at and campaign.recovered_order:
        events.append({
            'at': campaign.returned_at,
            'type': 'return',
            'title': 'Customer returned and purchased',
            'detail': (
                f"{campaign.product_summary} · "
                f"Rs. {campaign.recovered_revenue:.2f} associated return revenue."
            ),
        })

    if campaign.rescored_at and campaign.after_score is not None:
        events.append({
            'at': campaign.rescored_at,
            'type': 'score',
            'title': 'Post-campaign re-score',
            'detail': (
                f"{campaign.before_score:.2f} → {campaign.after_score:.2f} · "
                f"{campaign.get_outcome_display()}."
            ),
        })

    for complaint in resolved_complaints:
        events.append({
            'at': complaint.resolved_at,
            'type': 'complaint',
            'title': 'Complaint resolved',
            'detail': (
                f"{complaint.subject}. The live churn feature treats resolved "
                f"complaints as no active complaint."
            ),
        })

    if (
        latest_score
        and (
            campaign.rescored_at is None
            or latest_score.predicted_at > campaign.rescored_at
        )
    ):
        events.append({
            'at': latest_score.predicted_at,
            'type': 'current',
            'title': 'Latest customer churn state',
            'detail': (
                f"Latest saved score {latest_score.score:.2f} "
                f"({latest_score.risk_level.title()} risk)."
            ),
        })

    # All timestamps are persisted Django datetimes.
    return sorted(
        [event for event in events if event.get('at') is not None],
        key=lambda event: event['at'],
    )


@login_required
@user_passes_test(is_admin)
def retention_campaign_detail(request, campaign_id):
    """
    Full closed-loop view of ONE intervention.

    Important distinction:
      - campaign.after_score / outcome = the result measured immediately
        after the campaign-attributed paid return order.
      - latest_score = the customer's current saved churn state, which may
        change later because of complaint resolution or other behaviour.
    """
    campaign = get_object_or_404(
        RetentionCampaign.objects
        .select_related(
            'customer',
            'coupon',
            'notification',
            'source_score',
            'recovered_order',
        )
        .prefetch_related('recovered_order__items'),
        pk=campaign_id,
    )

    latest_score = (
        ChurnScore.objects
        .filter(customer=campaign.customer)
        .order_by('-predicted_at')
        .first()
    )

    before_features = (
        campaign.source_score.features
        if campaign.source_score and campaign.source_score.features
        else {}
    )
    current_features = (
        latest_score.features
        if latest_score and latest_score.features
        else {}
    )

    feature_changes = _retention_feature_changes(
        before_features,
        current_features,
    )

    resolved_complaints = list(
        Complaint.objects
        .filter(
            user=campaign.customer,
            status='RESOLVED',
            resolved_at__isnull=False,
            resolved_at__gte=campaign.sent_at,
        )
        .order_by('resolved_at')
    )

    timeline = _retention_campaign_timeline(
        campaign,
        resolved_complaints,
        latest_score,
    )

    current_score_change = None
    if latest_score is not None:
        current_score_change = round(
            latest_score.score - campaign.before_score,
            3,
        )

    campaign_score_change = campaign.score_change

    complaint_feature_change = next(
        (
            change for change in feature_changes
            if change['feature'] == 'Complain'
            and change['before'] == 1
            and change['after'] == 0
        ),
        None,
    )

    context = {
        'campaign': campaign,
        'latest_score': latest_score,
        'timeline': timeline,
        'feature_changes': feature_changes,
        'resolved_complaints': resolved_complaints,
        'complaint_feature_change': complaint_feature_change,
        'campaign_score_change': campaign_score_change,
        'current_score_change': current_score_change,
    }

    return render(request, 'churn/retention_detail.html', context)


@login_required
@user_passes_test(is_admin)
def export_high_risk_csv(request):
    """
    Downloads the current high-risk customer list as a CSV — same
    "latest score per customer" logic as the dashboard, filtered to
    risk_level='high'.
    """
    scores = (
        _latest_scores_queryset()
        .filter(risk_level='high')
        .select_related('customer')
        .order_by('-score')
    )

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="high_risk_customers.csv"'

    writer = csv.writer(response)
    writer.writerow(['Username', 'Email', 'Score', 'Risk Level', 'Last Scored'])

    for s in scores:
        writer.writerow([
            s.customer.username,
            s.customer.email,
            s.score,
            s.risk_level,
            s.predicted_at.strftime('%Y-%m-%d %H:%M'),
        ])

    return response