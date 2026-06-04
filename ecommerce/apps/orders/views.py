import base64
import hashlib
import hmac
import json
import uuid
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
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

    if product.stock <= 0:
        messages.error(
            request,
            f"'{product.name}' is out of stock."
        )
        return redirect(request.META.get('HTTP_REFERER', 'cart'))

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
        return redirect(request.META.get('HTTP_REFERER', 'cart'))

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
        return redirect(request.META.get('HTTP_REFERER', 'cart'))

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

    remove_quantity = request.POST.get('remove_quantity', 1)

    try:
        remove_quantity = int(remove_quantity)
    except ValueError:
        remove_quantity = 1

    if remove_quantity < 1:
        remove_quantity = 1

    if remove_quantity >= item.quantity:
        item.delete()

        messages.info(
            request,
            f"All '{product.name}' removed from cart."
        )
    else:
        item.quantity -= remove_quantity
        item.save()

        messages.info(
            request,
            f"{remove_quantity} '{product.name}' removed from cart."
        )

    UserEvent.objects.create(
        user=request.user,
        product=product,
        event_type='REMOVE_CART'
    )

    return redirect('cart')


def format_esewa_amount(value):
    amount = Decimal(value)

    if amount == amount.to_integral_value():
        return str(int(amount))

    return str(amount.normalize())

def generate_esewa_signature(message):
    secret_key = settings.ESEWA_SECRET_KEY.encode('utf-8')

    signature = hmac.new(
        secret_key,
        message.encode('utf-8'),
        hashlib.sha256
    ).digest()

    return base64.b64encode(signature).decode('utf-8')


def build_esewa_message(total_amount, transaction_uuid, product_code):
    return (
        f"total_amount={total_amount},"
        f"transaction_uuid={transaction_uuid},"
        f"product_code={product_code}"
    )


def build_esewa_response_message(response_data):
    signed_field_names = response_data.get('signed_field_names', '')
    fields = signed_field_names.split(',')

    message_parts = []

    for field in fields:
        value = response_data.get(field, '')
        message_parts.append(f"{field}={value}")

    return ",".join(message_parts)


def decode_esewa_response(encoded_data):
    decoded_bytes = base64.b64decode(encoded_data)
    decoded_string = decoded_bytes.decode('utf-8')
    return json.loads(decoded_string)


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

                # Check stock before starting payment
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

                transaction_uuid = f"ORDER-{uuid.uuid4().hex[:12]}"

                # Create unpaid order only. Do NOT reduce stock yet.
                order = Order.objects.create(
                    user=request.user,
                    total_price=cart.total_price,
                    payment_status='INITIATED',
                    payment_method='ESEWA',
                    transaction_uuid=transaction_uuid
                )
                
                UserEvent.objects.create(
                    user=request.user,
                    event_type='PAYMENT_STARTED'
                )

                for cart_item in cart_items:
                    product = cart_item.product

                    OrderItem.objects.create(
                        order=order,
                        product=product,
                        product_name=product.name,
                        price=product.effective_price,
                        quantity=cart_item.quantity
                    )

                amount = Decimal(order.total_price)
                tax_amount = Decimal("0")
                service_charge = Decimal("0")
                delivery_charge = Decimal("0")
                total_amount = amount + tax_amount + service_charge + delivery_charge

                amount_str = format_esewa_amount(amount)
                tax_amount_str = format_esewa_amount(tax_amount)
                service_charge_str = format_esewa_amount(service_charge)
                delivery_charge_str = format_esewa_amount(delivery_charge)
                total_amount_str = format_esewa_amount(total_amount)

                success_url = request.build_absolute_uri(
                    reverse('esewa_success')
                )

                failure_url = request.build_absolute_uri(
                    reverse('esewa_failure')
                )

                product_code = settings.ESEWA_PRODUCT_CODE

                signature_message = build_esewa_message(
                    total_amount_str,
                    transaction_uuid,
                    product_code
                )

                signature = generate_esewa_signature(
                    signature_message
                )

                esewa_data = {
                    'amount': amount_str,
                    'tax_amount': tax_amount_str,
                    'total_amount': total_amount_str,
                    'transaction_uuid': transaction_uuid,
                    'product_code': product_code,
                    'product_service_charge': service_charge_str,
                    'product_delivery_charge': delivery_charge_str,
                    'success_url': success_url,
                    'failure_url': failure_url,
                    'signed_field_names': 'total_amount,transaction_uuid,product_code',
                    'signature': signature,
                }

                return render(request, 'orders/esewa_redirect.html', {
                    'esewa_payment_url': settings.ESEWA_PAYMENT_URL,
                    'esewa_data': esewa_data,
                })

        except Exception as e:
            messages.error(
                request,
                f"Something went wrong while starting payment: {e}"
            )
            return redirect('checkout')

    return render(request, 'orders/checkout.html', {
        'cart': cart
    })


@login_required
def esewa_success(request):
    encoded_data = request.GET.get('data')

    if not encoded_data:
        messages.error(
            request,
            "Invalid eSewa response."
        )
        return redirect('cart')

    try:
        response_data = decode_esewa_response(encoded_data)

        transaction_uuid = response_data.get('transaction_uuid')
        status = response_data.get('status')
        received_signature = response_data.get('signature')

        order = get_object_or_404(
            Order,
            transaction_uuid=transaction_uuid,
            user=request.user
        )

        if order.payment_status == 'PAID':
            messages.info(
                request,
                "Payment already verified."
            )
            return redirect('order_detail', order_id=order.id)

        response_message = build_esewa_response_message(response_data)
        expected_signature = generate_esewa_signature(response_message)

        if received_signature != expected_signature:
            order.payment_status = 'FAILED'
            order.save()

            UserEvent.objects.create(
                user=request.user,
                event_type='PAYMENT_FAILED'
            )

            messages.error(
                request,
                "Payment verification failed. Invalid signature."
            )
            return redirect('cart')

        if status != 'COMPLETE':
            order.payment_status = 'FAILED'
            order.save()

            UserEvent.objects.create(
                user=request.user,
                event_type='PAYMENT_FAILED'
            )

            messages.error(
                request,
                "Payment was not completed."
            )
            return redirect('cart')

        with transaction.atomic():
            order_items = order.items.select_related('product')

            # Re-check stock only after payment success
            for item in order_items:
                product = item.product

                if product is None:
                    continue

                if item.quantity > product.stock:
                    order.payment_status = 'FAILED'
                    order.save()

                    UserEvent.objects.create(
                        user=request.user,
                        event_type='PAYMENT_FAILED'
                    )

                    messages.error(
                        request,
                        f"Payment received, but stock is not enough for '{item.product_name}'. Please contact support."
                    )
                    return redirect('cart')

            # Payment verified. Now reduce stock.
            for item in order_items:
                product = item.product

                if product is None:
                    continue

                product.stock -= item.quantity

                if product.stock < 0:
                    product.stock = 0

                product.save()

            order.payment_status = 'PAID'
            order.esewa_ref_id = response_data.get('transaction_code')
            order.paid_at = timezone.now()
            order.save()

            cart = Cart.objects.filter(
                user=request.user
            ).first()

            if cart:
                cart.items.all().delete()
            
            UserEvent.objects.create(
                user=request.user,
                event_type='PAYMENT_SUCCESS'
            )

            UserEvent.objects.create(
                user=request.user,
                event_type='ORDER'
            )

        messages.success(
            request,
            f"Payment successful. Order #{order.id} placed successfully!"
        )

        return redirect('order_detail', order_id=order.id)

    except Exception as e:
        messages.error(
            request,
            f"Could not verify eSewa payment: {e}"
        )
        return redirect('cart')


@login_required
def esewa_failure(request):
    UserEvent.objects.create(
        user=request.user,
        event_type='PAYMENT_FAILED'
    )

    messages.error(
        request,
        "eSewa payment failed or was cancelled."
    )

    return redirect('checkout')


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


@login_required
def order_list(request):
    orders = Order.objects.filter(
        user=request.user,
        payment_status='PAID'
    ).order_by('-created_at')

    return render(request, 'orders/order_list.html', {
        'orders': orders
    })


@login_required
def order_detail(request, order_id):
    order = get_object_or_404(
        Order,
        id=order_id,
        user=request.user,
        payment_status='PAID'
    )

    return render(request, 'orders/order_detail.html', {
        'order': order
    })


@login_required
def cancel_order(request, order_id):
    order = get_object_or_404(
        Order,
        id=order_id,
        user=request.user,
        payment_status='PAID'
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