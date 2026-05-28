from django.shortcuts import render
from django.http import JsonResponse
from .models import UserEvent
from apps.products.models import Product

# Create your views here.

def log_click(
    request,
    product_id
):

    if request.user.is_authenticated:

        product=Product.objects.get(
            id=product_id
        )

        UserEvent.objects.create(

            user=request.user,
            product=product,
            event_type='CLICK'
        )

    return JsonResponse({
        "success":True
    })