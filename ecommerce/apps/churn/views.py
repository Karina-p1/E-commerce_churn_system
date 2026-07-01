from django.shortcuts import render
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth import get_user_model
from django.db.models import Avg, OuterRef, Subquery
from .models import ChurnScore

User = get_user_model()


def is_admin(user):
    return user.is_staff or user.is_superuser


@login_required
@user_passes_test(is_admin)
def churn_dashboard(request):

    # Latest score per customer only
    latest_scores = (
        ChurnScore.objects
        .filter(customer=OuterRef('customer'))
        .order_by('-predicted_at')
        .values('id')[:1]
    )

    scores = (
        ChurnScore.objects
        .filter(id__in=Subquery(latest_scores))
        .select_related('customer')
        .order_by('-score')
    )

    # Filter by risk level if requested
    risk_filter = request.GET.get('risk', 'all')
    if risk_filter in ('high', 'low'):
        scores = scores.filter(risk_level=risk_filter)

    # Summary counts — always from the full unfiltered latest-score set
    all_scores = ChurnScore.objects.filter(
        id__in=Subquery(
            ChurnScore.objects
            .filter(customer=OuterRef('customer'))
            .order_by('-predicted_at')
            .values('id')[:1]
        )
    )

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