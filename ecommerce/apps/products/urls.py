from django.urls import path
from . import views

app_name = 'products'

urlpatterns = [
    path('', views.view_products, name='view_products'),

    path('wishlist/', views.wishlist_view, name='wishlist'),
    path('wishlist/add/<int:product_id>/', views.add_to_wishlist, name='add_to_wishlist'),
    path('wishlist/remove/<int:product_id>/', views.remove_from_wishlist, name='remove_from_wishlist'),
    path('api/top-products/', views.top_products, name='top_products'),
    path('api/search/', views.search_autocomplete, name='search_autocomplete'), 

    path('<slug:slug>/review/', views.post_review, name='post_review'),
    path('<slug:slug>/', views.product_detail, name='product_detail'),
]