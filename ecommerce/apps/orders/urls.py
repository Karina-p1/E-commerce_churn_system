from django.urls import path
from . import views

urlpatterns = [
    path('cart/', views.cart_view, name='cart'),
    path('cart/add/<int:product_id>/', views.add_to_cart, name='add_to_cart'),
    path('cart/remove/<int:item_id>/', views.remove_from_cart, name='remove_from_cart'),
    path('checkout/', views.checkout_view, name='checkout'),

    path('orders/', views.order_list, name='order_list'),
    path('orders/<int:order_id>/', views.order_detail, name='order_detail'),
    path('orders/<int:order_id>/cancel/', views.cancel_order, name='cancel_order'),
    path('payment/failed/', views.payment_failed, name='payment_failed'),
    
    path('payment/esewa/success/', views.esewa_success, name='esewa_success'),
    path('payment/esewa/failure/', views.esewa_failure, name='esewa_failure'),

    path('order_list/', views.order_list_admin, name='order_list_admin'),
    path('order_list/<int:pk>/', views.order_detail_admin, name='order_detail_admin'),
    path('order_list/<int:pk>/update-status/', views.order_update_status, name='order_update_status'),
    path('order_list/<int:pk>/cancel/', views.order_cancel, name='order_cancel'),
]