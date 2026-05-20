from django.urls import path
from .views import view_products

urlpatterns = [
    path('dashboard/', view_products, name='view_products'),
]
