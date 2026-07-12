from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET

from .models import UserEvent
from apps.products.models import Product
from django.contrib.auth.decorators import login_required
from django.utils import timezone

from .models import UserSession

@require_GET
def log_click(request, product_id):
    if not request.user.is_authenticated:
        return JsonResponse({
            "success": False,
            "message": "User not authenticated"
        }, status=401)

    product = get_object_or_404(
        Product,
        id=product_id,
        is_active=True
    )

    UserEvent.objects.create(
        user=request.user,
        product=product,
        event_type='CLICK'
    )

    return JsonResponse({
        "success": True,
        "message": "Click logged successfully"
    })
    
@login_required
def activity_ping(request):

    if request.method != "POST":
        return JsonResponse({"success": False})

    session = (
        UserSession.objects
        .filter(
            user=request.user,
            ended_at__isnull=True
        )
        .order_by("-started_at")
        .first()
    )

    if session:
        elapsed = (
            timezone.now() -
            session.last_activity
        ).total_seconds()

        session.active_seconds += min(
            int(elapsed),
            60
        )

        session.last_activity = timezone.now()

        session.save(
            update_fields=[
                "active_seconds",
                "last_activity",
            ]
        )

    return JsonResponse({"success": True})