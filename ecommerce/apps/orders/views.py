from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from apps.products.models import Product
from apps.activity.models import UserEvent

from .models import Cart, CartItem, Order, OrderItem


@login_required
def cart_view(request):
    cart, _ = Cart.objects.get_or_create(user=request.user)

    return render(request, 'orders/cart.html', {
        'cart': cart
    })


@login_required
def add_to_cart(request, product_id):
    product = get_object_or_404(
        Product,
        id=product_id,
        is_active=True
    )

    cart, _ = Cart.objects.get_or_create(
        user=request.user
    )

    quantity = request.POST.get('quantity', 1)
    action = request.POST.get('action', 'cart')

    try:
        quantity = int(quantity)
    except ValueError:
        quantity = 1

    if quantity < 1:
        quantity = 1

    item, created = CartItem.objects.get_or_create(
        cart=cart,
        product=product
    )

    if created:
        item.quantity = quantity
    else:
        item.quantity += quantity

    item.save()

    UserEvent.objects.create(
        user=request.user,
        product=product,
        event_type='CART'
    )

    if action == 'buy':
        messages.success(
            request,
            f"'{product.name}' added to cart. Continue checkout."
        )
        return redirect('checkout')

    messages.success(
        request,
        f"'{product.name}' added to cart."
    )

    return redirect('cart')


@login_required
def remove_from_cart(request, item_id):
    item = get_object_or_404(
        CartItem,
        id=item_id,
        cart__user=request.user
    )

    product = item.product

    item.delete()

    # Activity tracking: Remove from cart
    UserEvent.objects.create(
        user=request.user,
        product=product,
        event_type='REMOVE_CART'
    )

    messages.info(
        request,
        "Item removed from cart."
    )

    return redirect('cart')


@login_required
def checkout_view(request):
    cart, _ = Cart.objects.get_or_create(
        user=request.user
    )

    if not cart.items.exists():
        messages.warning(
            request,
            "Your cart is empty."
        )

        return redirect('cart')

    if request.method == 'POST':
        order = Order.objects.create(
            user=request.user,
            total_price=cart.total_price
        )

        for cart_item in cart.items.all():
            OrderItem.objects.create(
                order=order,
                product=cart_item.product,
                product_name=cart_item.product.name,
                price=cart_item.product.price,
                quantity=cart_item.quantity
            )

        # Activity tracking: Order placed
        UserEvent.objects.create(
            user=request.user,
            event_type='ORDER'
        )

        cart.items.all().delete()

        messages.success(
            request,
            f"Order #{order.id} placed successfully!"
        )

        return redirect(
            'order_detail',
            order_id=order.id
        )

    return render(request, 'orders/checkout.html', {
        'cart': cart
    })


@login_required
def order_list(request):
    orders = Order.objects.filter(
        user=request.user
    ).order_by('-created_at')

    return render(request, 'orders/order_list.html', {
        'orders': orders
    })


@login_required
def order_detail(request, order_id):
    order = get_object_or_404(
        Order,
        id=order_id,
        user=request.user
    )

    return render(request, 'orders/order_detail.html', {
        'order': order
    })