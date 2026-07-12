import csv

from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth import get_user_model
from django.db.models import Avg, OuterRef, Subquery

from .models import ChurnScore
from .features import extract_features
from .predictor import predict_churn

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

    scores = (
        _latest_scores_queryset()
        .select_related('customer')
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
def churn_customer_detail(request, customer_id):
    """
    Drill-down page for a single customer: their full current feature
    breakdown (recomputed live, so it's always up to date even if they've
    acted since the last score_customers run) plus their score history
    for the trend chart.
    """
    customer = get_object_or_404(User, id=customer_id, is_staff=False, is_superuser=False)

    features = extract_features(customer)
    result = predict_churn(features)

    history = (
        ChurnScore.objects
        .filter(customer=customer)
        .order_by('predicted_at')
    )

    # Data for the Chart.js line chart — dates + scores as parallel lists
    history_labels = [h.predicted_at.strftime('%b %d, %Y %H:%M') for h in history]
    history_scores = [h.score for h in history]

    latest_saved = history.last()

    context = {
        'customer':        customer,
        'features':        features,
        'result':          result,
        'history':         history,
        'history_labels':  history_labels,
        'history_scores':  history_scores,
        'latest_saved':    latest_saved,
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