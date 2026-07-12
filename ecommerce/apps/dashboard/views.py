from datetime import timedelta
from decimal import Decimal

from django.apps import apps
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import get_user_model
from django.db.models import Count, Sum, Avg, F
from django.db.models.functions import TruncDate
from django.shortcuts import render
from django.utils import timezone

from apps.products.models import Product, Category, Brand, Wishlist


@staff_member_required
def admin_profile(request):
    return render(request, "dashboard/admin_profile.html")