from django.urls import path
from . import views

app_name = 'products'

urlpatterns = [
    path('', views.view_products, name='view_products'),
    path('<slug:slug>/', views.product_detail, name='product_detail'),
    path('<slug:slug>/review/', views.post_review, name='post_review'),
]
