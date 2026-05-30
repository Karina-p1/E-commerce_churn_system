from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET

from .models import UserEvent
from apps.products.models import Product


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