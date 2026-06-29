from django.urls import path
from . import views

app_name = 'products'

urlpatterns = [
    path('', views.view_products, name='view_products'),

    path('wishlist/', views.wishlist_view, name='wishlist'),
    path('wishlist/add/<int:product_id>/',
         views.add_to_wishlist, name='add_to_wishlist'),
    path('wishlist/remove/<int:product_id>/',
         views.remove_from_wishlist, name='remove_from_wishlist'),
    path('api/top-products/', views.top_products, name='top_products'),

   # Categories
    path('categories/', views.category_list, name='category_list'),
    path('categories/add/', views.category_add, name='category_add'),
    path('categories/<int:pk>/edit/', views.category_edit, name='category_edit'),
    path('categories/<int:pk>/delete/', views.category_delete_confirm, name='category_delete_confirm'),

    # Brands
    path('brands/', views.brand_list, name='brand_list'),
    path('brands/add/', views.brand_add, name='brand_add'),
    path('brands/<int:pk>/edit/', views.brand_edit, name='brand_edit'),
    path('brands/<int:pk>/delete/', views.brand_delete_confirm, name='brand_delete_confirm'),

    # Products (management)
    path('products/', views.product_list, name='product_list'),
    path('products/add/', views.product_add, name='product_add'),
    path('products/<int:pk>/edit/', views.product_edit, name='product_edit'),
    path('products/<int:pk>/delete/', views.product_delete_confirm, name='product_delete_confirm'),

    # Users
    path('users/', views.user_list, name='user_list'),
    path('users/<int:pk>/toggle-active/', views.user_toggle_active, name='user_toggle_active'),
    path('users/<int:pk>/delete/', views.user_delete_confirm, name='user_delete_confirm'),

    # Catch-all slug patterns — MUST stay last, or they swallow everything above
    path('<slug:slug>/review/', views.post_review, name='post_review'),
    path('<slug:slug>/', views.product_detail, name='product_detail'),
]