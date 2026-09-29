import csv

from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth import get_user_model
from django.db.models import Avg, OuterRef, Subquery, Count, Q

from .models import ChurnScore
from .features import extract_features, extract_features_with_metadata
from .predictor import predict_churn
from .services import score_all_customers

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