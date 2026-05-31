from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction

from apps.products.models import Product
from apps.activity.models import UserEvent

from .models import Cart, CartItem, Order, OrderItem
from .models import Order

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

    if product.stock <= 0:
        messages.error(
            request,
            f"'{product.name}' is out of stock."
        )

        return redirect(
            request.META.get('HTTP_REFERER', 'cart')
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

    if quantity > product.stock:
        messages.error(
            request,
            f"Only {product.stock} unit(s) of '{product.name}' are available."
        )

        return redirect(
            request.META.get('HTTP_REFERER', 'cart')
        )

    item, created = CartItem.objects.get_or_create(
        cart=cart,
        product=product
    )

    existing_quantity = 0 if created else item.quantity
    new_quantity = existing_quantity + quantity

    if new_quantity > product.stock:
        messages.error(
            request,
            f"You already have {existing_quantity} in cart. Only {product.stock} unit(s) available."
        )

        return redirect(
            request.META.get('HTTP_REFERER', 'cart')
        )

    item.quantity = new_quantity
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

    if request.method == 'GET':
        UserEvent.objects.create(
            user=request.user,
            event_type='CHECKOUT_STARTED'
        )

    if request.method == 'POST':

        try:
            with transaction.atomic():

                cart_items = cart.items.select_related('product')

                # Check stock before creating order
                for cart_item in cart_items:
                    product = cart_item.product

                    if product.stock <= 0:
                        messages.error(
                            request,
                            f"'{product.name}' is out of stock."
                        )
                        return redirect('cart')

                    if cart_item.quantity > product.stock:
                        messages.error(
                            request,
                            f"Only {product.stock} unit(s) of '{product.name}' are available."
                        )
                        return redirect('cart')

                order = Order.objects.create(
                    user=request.user,
                    total_price=cart.total_price
                )

                # Create order items and reduce stock
                for cart_item in cart_items:
                    product = cart_item.product

                    OrderItem.objects.create(
                        order=order,
                        product=product,
                        product_name=product.name,
                        price=product.price,
                        quantity=cart_item.quantity
                    )

                    product.stock -= cart_item.quantity

                    if product.stock < 0:
                        product.stock = 0

                    product.save()

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

        except Exception as e:
            messages.error(
                request,
                f"Something went wrong while placing your order: {e}"
            )

            return redirect('checkout')

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

@login_required
def cancel_order(request, order_id):
    order = get_object_or_404(
        Order,
        id=order_id,
        user=request.user
    )

    if order.status in ['pending', 'processing']:
        order.status = 'cancelled'
        order.save()

        UserEvent.objects.create(
            user=request.user,
            event_type='ORDER_CANCELLED'
        )

        messages.success(
            request,
            f"Order #{order.id} cancelled successfully."
        )
    else:
        messages.warning(
            request,
            "This order cannot be cancelled."
        )

    return redirect(
        'order_detail',
        order_id=order.id
    )

@login_required
def payment_failed(request):
    UserEvent.objects.create(
        user=request.user,
        event_type='PAYMENT_FAILED'
    )

    messages.error(
        request,
        "Payment failed. Please try again."
    )

    return redirect('checkout')