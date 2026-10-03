from django.conf import settings
import base64
import hashlib
import hmac
import json
import re
import uuid
from decimal import Decimal
from django.contrib.admin.views.decorators import staff_member_required
from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.http import JsonResponse, request
from django.urls import reverse
from django.utils import timezone
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from apps.analytics.tasks import order_refunded, paid_order_created
from apps.products.models import Product
from apps.activity.models import UserEvent
from apps.addresses.models import Address
from apps.notifications.models import Notification
from apps.orders.task import send_payment_reminder
from ecommerce.validators import (
    parse_choice,
    parse_datetime_input,
    parse_decimal,
    parse_int,
    parse_text,
)
from .forms import RefundRequestForm

from .models import Cart, CartItem, Order, OrderItem, Coupon
from django.core.paginator import Paginator
from django.db.models import Q
SESSION_COUPON_KEY = 'applied_coupon_code'
ORDER_STATUS_SEQUENCE = ['pending', 'processing', 'shipped', 'delivered']
PAYMENT_METHOD_CHOICES = [('ESEWA', 'eSewa'), ('COD', 'Cash on Delivery')]

from apps.loyalty.models import LoyaltyAccount
from apps.loyalty.services import LoyaltyService


def _get_cart_items_payload(cart):
    """Flattened {'price', 'quantity'} list used for BUY_X_GET_Y calculations."""
    return [
        {'price': item.product.effective_price, 'quantity': item.quantity}
        for item in cart.items.select_related('product')
    ]


def _get_session_coupon(request, cart):
    """
    Looks up the coupon code (if any) stored in session, re-validates it
    against the current cart (amount, quantity, and the requesting user for
    FIRST_ORDER-type coupons), and returns a tuple:
        (coupon_or_None, discount_amount)

    If the stored coupon is no longer valid, it is silently cleared from the
    session and (None, Decimal('0')) is returned.
    """
    code = request.session.get(SESSION_COUPON_KEY)

    if not code:
        return None, Decimal('0')

    try:
        coupon = Coupon.objects.get(code__iexact=code)
    except Coupon.DoesNotExist:
        request.session.pop(SESSION_COUPON_KEY, None)
        return None, Decimal('0')

    order_amount = cart.total_price
    cart_quantity = cart.total_items

    is_valid, _ = coupon.is_valid(
        order_amount=order_amount,
        user=request.user,
        cart_quantity=cart_quantity,
    )

    if not is_valid:
        request.session.pop(SESSION_COUPON_KEY, None)
        return None, Decimal('0')

    discount_amount = coupon.calculate_discount(
        order_amount,
        cart_items=_get_cart_items_payload(cart),
    )
    return coupon, discount_amount


@login_required
def cart_view(request):
    cart, _ = Cart.objects.get_or_create(
        user=request.user
    )

    shipping_fee = LoyaltyService.get_shipping_fee(
        request.user
    )

    cart_total = Decimal(str(cart.total_price))

    final_total = cart_total + shipping_fee

    return render(request, 'orders/cart.html', {
        'cart': cart,
        'shipping_fee': shipping_fee,
        'final_total': final_total,
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
def apply_coupon(request):
    if request.method != 'POST':
        return JsonResponse(
            {'success': False, 'error': 'Invalid request method.'},
            status=405
        )

    code = (request.POST.get('code') or '').strip().upper()

    if not code:
        return JsonResponse({'success': False, 'error': 'Please enter a coupon code.'})

    cart, _ = Cart.objects.get_or_create(user=request.user)

    if not cart.items.exists():
        return JsonResponse({'success': False, 'error': 'Your cart is empty.'})

    try:
        coupon = Coupon.objects.get(code__iexact=code)
    except Coupon.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Invalid coupon code.'})

    cart_total = cart.total_price
    cart_quantity = cart.total_items

    is_valid, error_message = coupon.is_valid(
        order_amount=cart_total,
        user=request.user,
        cart_quantity=cart_quantity,
    )

    if not is_valid:
        return JsonResponse({'success': False, 'error': error_message})

    discount_amount = coupon.calculate_discount(
        cart_total,
        cart_items=_get_cart_items_payload(cart),
    )
    final_total = cart_total - discount_amount

    request.session[SESSION_COUPON_KEY] = coupon.code

    return JsonResponse({
        'success': True,
        'message': f"Coupon '{coupon.code}' applied successfully.",
        'discount_amount': str(discount_amount),
        'final_total': str(final_total),
    })


@login_required
def checkout_view(request):
    cart, _ = Cart.objects.get_or_create(
        user=request.user
    )
    
    # Get or create loyalty account
    loyalty_account = LoyaltyService.get_or_create_account(
        request.user
    )

    # Calculate shipping fee based on loyalty tier
    shipping_fee = LoyaltyService.get_shipping_fee(
        request.user
    )

    addresses = Address.objects.filter(
        user=request.user
    ).order_by(
        "-is_default",
        "-created_at"
    )

    payment_method = request.POST.get("payment_method")

    if not cart.items.exists():
        messages.warning(
            request,
            "Your cart is empty."
        )
        return redirect("cart")

    if not addresses.exists():
        messages.warning(
            request,
            "Please add a delivery address first."
        )
        return redirect("addresses:add_address")

    # ---------------------------------------------------------
    # PAYMENT METHOD
    # ---------------------------------------------------------
    # This is a plain radio group, not a Django form, so an unrecognised
    # or missing value used to be written straight onto the order. An
    # unknown value then fell through the `if payment_method == "COD"`
    # branch below and sent the customer to an eSewa checkout for an
    # order they never chose.
    if request.method == "POST":
        payment_method, payment_method_error = parse_choice(
            payment_method,
            "payment method",
            PAYMENT_METHOD_CHOICES,
        )

        if payment_method_error:
            messages.error(request, payment_method_error)
            return redirect("checkout")

    # ---------------------------------------------------------
    # GET REQUEST
    # ---------------------------------------------------------
    if request.method == "GET":
        UserEvent.objects.create(
            user=request.user,
            event_type="CHECKOUT_STARTED"
        )

    # ---------------------------------------------------------
    # POST REQUEST
    # ---------------------------------------------------------
    if request.method == "POST":

        selected_address_id = request.POST.get("address")

        if not selected_address_id:
            messages.error(
                request,
                "Please select a delivery address."
            )
            return redirect("checkout")

        try:
            selected_address = get_object_or_404(
                Address,
                id=selected_address_id,
                user=request.user
            )

            with transaction.atomic():

                # -------------------------------------------------
                # CHECK STOCK
                # -------------------------------------------------
                cart_items = cart.items.select_related("product")

                for cart_item in cart_items:
                    product = cart_item.product

                    if product.stock <= 0:
                        messages.error(
                            request,
                            f"'{product.name}' is out of stock."
                        )
                        return redirect("cart")

                    if cart_item.quantity > product.stock:
                        messages.error(
                            request,
                            f"Only {product.stock} unit(s) of "
                            f"'{product.name}' are available."
                        )
                        return redirect("cart")

                # -------------------------------------------------
                # TRANSACTION UUID
                # -------------------------------------------------
                transaction_uuid = (
                    f"ORDER-{uuid.uuid4().hex[:12]}"
                )

                # -------------------------------------------------
                # ADDRESS
                # -------------------------------------------------
                address_id = request.POST.get("address")

                if not address_id:
                    messages.error(
                        request,
                        "Please select a delivery address."
                    )
                    return redirect("checkout")

                address = get_object_or_404(
                    Address,
                    id=address_id,
                    user=request.user
                )

                # -------------------------------------------------
                # COUPON
                # -------------------------------------------------
                coupon_obj, discount_amount = _get_session_coupon(
                    request,
                    cart
                )

                cart_total = Decimal(str(cart.total_price))
                discount_amount = Decimal(str(discount_amount))

                amount_after_coupon = (
                    cart_total - discount_amount
                )

                amount_after_coupon = max(
                    Decimal("0.00"),
                    amount_after_coupon
                )

                # -------------------------------------------------
                # LOYALTY POINT REDEMPTION
                # -------------------------------------------------
                try:
                    requested_loyalty_points = int(
                        request.POST.get(
                            "loyalty_points",
                            "0"
                        ) or 0
                    )
                except (TypeError, ValueError):
                    messages.error(
                        request,
                        "Invalid loyalty points value."
                    )
                    return redirect("checkout")

                if requested_loyalty_points < 0:
                    messages.error(
                        request,
                        "Loyalty points cannot be negative."
                    )
                    return redirect("checkout")

                # Redemption must happen in 100-point blocks
                if requested_loyalty_points % 100 != 0:
                    messages.error(
                        request,
                        "Loyalty points must be redeemed in multiples of 100."
                    )
                    return redirect("checkout")

                actual_loyalty_points = 0
                loyalty_discount = Decimal("0.00")

                if requested_loyalty_points > 0:

                    # Refresh the account so we use the latest balance
                    loyalty_account = (
                        LoyaltyAccount.objects
                        .select_for_update()
                        .get(user=request.user)
                    )

                    # Check available balance
                    if (
                        requested_loyalty_points
                        > loyalty_account.available_points
                    ):
                        messages.error(
                            request,
                            "You do not have enough loyalty points."
                        )
                        return redirect("checkout")

                    # 100 points = Rs. 50
                    requested_loyalty_discount = (
                        LoyaltyService.calculate_reward_value(
                            requested_loyalty_points
                        )
                    )

                    # The customer cannot redeem more points
                    # than the amount remaining after coupon.
                    max_redeemable_points = int(
                        amount_after_coupon / Decimal("0.50")
                    )

                    # Keep redemption in 100-point blocks
                    max_redeemable_points = (
                        max_redeemable_points // 100
                    ) * 100

                    if requested_loyalty_points > max_redeemable_points:
                        messages.error(
                            request,
                            "You cannot redeem that many points "
                            "for this order."
                        )
                        return redirect("checkout")

                    actual_loyalty_points = (
                        requested_loyalty_points
                    )

                    loyalty_discount = (
                        requested_loyalty_discount
                    )

                # -------------------------------------------------
                # FINAL ORDER TOTAL
                # -------------------------------------------------

                final_total = (
                    amount_after_coupon
                    - loyalty_discount
                    + shipping_fee
                )

                final_total = max(
                    Decimal("0.00"),
                    final_total
                )

                # -------------------------------------------------
                # CREATE ORDER
                # -------------------------------------------------
                order = Order.objects.create(
                    user=request.user,

                    total_price=final_total,

                    coupon=coupon_obj,
                    discount_amount=discount_amount,

                    # Loyalty information
                    loyalty_points_redeemed=actual_loyalty_points,
                    loyalty_discount_amount=loyalty_discount,
                    
                    shipping_fee=shipping_fee,

                    payment_status="INITIATED",
                    payment_method=payment_method,
                    transaction_uuid=transaction_uuid,

                    delivery_label=selected_address.label,
                    delivery_full_name=selected_address.full_name,
                    delivery_phone=selected_address.phone,

                    delivery_province=selected_address.province,
                    delivery_district=selected_address.district,
                    delivery_city=selected_address.city,
                    delivery_ward=selected_address.ward,
                    delivery_street=selected_address.street,
                    delivery_landmark=selected_address.landmark,

                    delivery_latitude=selected_address.latitude,
                    delivery_longitude=selected_address.longitude,
                )

                order.status_history.create(
                    status="pending"
                )

                # -------------------------------------------------
                # PAYMENT STARTED EVENT
                # -------------------------------------------------
                UserEvent.objects.create(
                    user=request.user,
                    event_type="PAYMENT_STARTED"
                )

                # -------------------------------------------------
                # PAYMENT REMINDER
                # -------------------------------------------------
                transaction.on_commit(
                    lambda oid=order.id: send_payment_reminder.apply_async(
                        args=[oid],
                        countdown=120
                    )
                )

                # -------------------------------------------------
                # CREATE ORDER ITEMS
                # -------------------------------------------------
                for cart_item in cart_items:
                    product = cart_item.product

                    OrderItem.objects.create(
                        order=order,
                        product=product,
                        product_name=product.name,
                        price=product.effective_price,
                        quantity=cart_item.quantity
                    )

                # -------------------------------------------------
                # COD PAYMENT
                # -------------------------------------------------
                if payment_method == "COD":

                    order.payment_status = "UNPAID"
                    order.save(
                        update_fields=[
                            "payment_status",
                            "updated_at"
                        ]
                    )

                    # Coupon usage is incremented for the order
                    if order.coupon:
                        Coupon.objects.filter(
                            pk=order.coupon_id
                        ).update(
                            used_count=F("used_count") + 1
                        )

                    # Loyalty points are NOT deducted here.
                    # They will be deducted when the COD order
                    # becomes PAID through paid_order_created.

                    request.session.pop(
                        SESSION_COUPON_KEY,
                        None
                    )

                    cart.items.all().delete()

                    messages.success(
                        request,
                        "Your order has been placed successfully."
                    )

                    return redirect(
                        "order_detail",
                        order.id
                    )

                # -------------------------------------------------
                # ESEWA PAYMENT
                # -------------------------------------------------
                amount = Decimal(order.total_price)

                tax_amount = Decimal("0")
                service_charge = Decimal("0")
                delivery_charge = Decimal("0")

                total_amount = (
                    amount
                    + tax_amount
                    + service_charge
                    + delivery_charge
                )

                amount_str = format_esewa_amount(
                    amount
                )

                tax_amount_str = format_esewa_amount(
                    tax_amount
                )

                service_charge_str = format_esewa_amount(
                    service_charge
                )

                delivery_charge_str = format_esewa_amount(
                    delivery_charge
                )

                total_amount_str = format_esewa_amount(
                    total_amount
                )

                success_url = request.build_absolute_uri(
                    reverse("esewa_success")
                )

                failure_url = request.build_absolute_uri(
                    reverse("esewa_failure")
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
                    "amount": amount_str,
                    "tax_amount": tax_amount_str,
                    "total_amount": total_amount_str,
                    "transaction_uuid": transaction_uuid,
                    "product_code": product_code,
                    "product_service_charge": service_charge_str,
                    "product_delivery_charge": delivery_charge_str,
                    "success_url": success_url,
                    "failure_url": failure_url,
                    "signed_field_names": (
                        "total_amount,"
                        "transaction_uuid,"
                        "product_code"
                    ),
                    "signature": signature,
                }

                # Coupon and loyalty values are already
                # stored on the Order.
                request.session.pop(
                    SESSION_COUPON_KEY,
                    None
                )

                return render(
                    request,
                    "orders/esewa_redirect.html",
                    {
                        "esewa_payment_url": (
                            settings.ESEWA_PAYMENT_URL
                        ),
                        "esewa_data": esewa_data,
                    }
                )

        except Exception as e:
            messages.error(
                request,
                f"Something went wrong while starting payment: {e}"
            )
            return redirect("checkout")

    # =========================================================
    # GET: DISPLAY CHECKOUT
    # =========================================================

    applied_coupon, discount_amount = _get_session_coupon(
        request,
        cart
    )

    cart_total = Decimal(str(cart.total_price))
    discount_amount = Decimal(str(discount_amount))

    amount_after_coupon = (
        cart_total - discount_amount
    )

    amount_after_coupon = max(
        Decimal("0.00"),
        amount_after_coupon
    )

    # No loyalty points are redeemed until the user
    # submits the checkout form.
    loyalty_discount = Decimal("0.00")
    loyalty_points_redeemed = 0

    final_total = (
        amount_after_coupon
        - loyalty_discount
        + shipping_fee
    )

    final_total = max(
        Decimal("0.00"),
        final_total
    )

    return render(
        request,
        "orders/checkout.html",
        {
            "cart": cart,
            "addresses": addresses,

            "coupon": applied_coupon,
            "discount_amount": discount_amount,

            "cart_total": cart_total,
            "final_total": final_total,

            # Loyalty information
            "loyalty_account": loyalty_account,
            "loyalty_discount": loyalty_discount,
            "loyalty_points_redeemed": (
                loyalty_points_redeemed
            ),
            
            "shipping_fee": shipping_fee,
        }
    )


@login_required
def esewa_success(request):
    encoded_data = request.GET.get("data")

    if not encoded_data:
        messages.error(
            request,
            "Invalid eSewa response."
        )
        return redirect("cart")

    try:
        response_data = decode_esewa_response(encoded_data)

        transaction_uuid = response_data.get("transaction_uuid")
        status = response_data.get("status")
        received_signature = response_data.get("signature")

        order = get_object_or_404(
            Order,
            transaction_uuid=transaction_uuid,
            user=request.user
        )

        # Already paid
        if order.payment_status == "PAID":
            messages.info(
                request,
                "Payment already verified."
            )
            return redirect(
                "order_detail",
                order_id=order.id
            )

        # Verify signature
        response_message = build_esewa_response_message(response_data)
        expected_signature = generate_esewa_signature(response_message)

        if received_signature != expected_signature:

            order.payment_status = "FAILED"
            order.save(update_fields=["payment_status"])

            UserEvent.objects.create(
                user=request.user,
                event_type="PAYMENT_FAILED"
            )

            messages.error(
                request,
                "Payment verification failed. Invalid signature."
            )

            return redirect("cart")

        # Verify payment status
        if status != "COMPLETE":

            order.payment_status = "FAILED"
            order.save(update_fields=["payment_status"])

            UserEvent.objects.create(
                user=request.user,
                event_type="PAYMENT_FAILED"
            )

            messages.error(
                request,
                "Payment was not completed."
            )

            return redirect("cart")

        with transaction.atomic():

            order_items = order.items.select_related("product")

            # Check stock again
            for item in order_items:

                product = item.product

                if product is None:
                    continue

                if item.quantity > product.stock:

                    order.payment_status = "FAILED"
                    order.save(update_fields=["payment_status"])

                    UserEvent.objects.create(
                        user=request.user,
                        event_type="PAYMENT_FAILED"
                    )

                    messages.error(
                        request,
                        f"Payment received, but stock is not enough for '{item.product_name}'. Please contact support."
                    )

                    return redirect("cart")

            # Reduce stock
            for item in order_items:

                product = item.product

                if product is None:
                    continue

                product.stock -= item.quantity

                if product.stock < 0:
                    product.stock = 0

                product.save(update_fields=["stock"])

            # Mark order as paid
            order.payment_status = "PAID"
            order.esewa_ref_id = response_data.get("transaction_code")
            order.paid_at = timezone.now()

            order.save(
                update_fields=[
                    "payment_status",
                    "esewa_ref_id",
                    "paid_at",
                ]
            )

            # ✅ IMPORTANT
            # Queue analytics update AFTER database commit
            transaction.on_commit(
                lambda: paid_order_created.delay(order.id)
            )

            # Retention attribution happens only after a real paid order.
            # It records product names/revenue and re-scores the customer.
            from apps.churn.tasks import process_retention_order_task
            transaction.on_commit(
                lambda oid=order.id: process_retention_order_task.delay(oid)
            )

            # Update coupon usage
            if order.coupon:
                Coupon.objects.filter(
                    pk=order.coupon_id
                ).update(
                    used_count=F("used_count") + 1
                )

            # Empty cart
            cart = Cart.objects.filter(
                user=request.user
            ).first()

            if cart:
                cart.items.all().delete()

            # Activity logs
            UserEvent.objects.create(
                user=request.user,
                event_type="PAYMENT_SUCCESS"
            )

            UserEvent.objects.create(
                user=request.user,
                event_type="ORDER"
            )

        messages.success(
            request,
            f"Payment successful. Order #{order.id} placed successfully!"
        )

        return redirect(
            "order_detail",
            order_id=order.id
        )

    except Exception as e:

        messages.error(
            request,
            f"Could not verify eSewa payment: {e}"
        )

        return redirect("cart")


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
        is_hidden=False,
    ).select_related("coupon").order_by("-created_at")

    return render(request, 'orders/order_list.html', {
        'orders': orders
    })

@login_required
def hide_order(request, order_id):
    if request.method != "POST":
        return redirect("order_list")

    order = get_object_or_404(
        Order,
        id=order_id,
        user=request.user
    )

    # Finished orders, or orders whose payment was started but never completed
    is_finished = order.status in ["delivered", "cancelled"]
    is_unfinished_payment = order.payment_status in ["INITIATED", "FAILED"]

    can_hide = (
        (is_finished or is_unfinished_payment)
        and order.refund_status != "PENDING"
    )

    if can_hide:
        order.is_hidden = True
        order.save(update_fields=["is_hidden"])
        messages.success(request, "Order removed from your list.")
    else:
        messages.error(request, "This order can't be removed right now.")

    return redirect("order_list")

@login_required
def order_detail(request, order_id):
    order = get_object_or_404(
        Order,
        id=order_id,
        user=request.user,
    )

    # Build the visual timeline from REAL OrderStatusHistory rows, not
    # just the order's current status — so if an order skipped straight
    # from pending to shipped, the timeline shows exactly that, instead
    # of pretending every step happened. Only built for orders that are
    # still progressing normally; a cancelled order breaks the linear
    # flow entirely, so it gets its own separate alert block instead
    # (already in the template) rather than being forced into this.
    timeline = None
    timeline_fill_percent = 0
    if order.status != 'cancelled':
        history_by_status = {
            h.status: h for h in order.status_history.all()
        }
        current_index = (
            ORDER_STATUS_SEQUENCE.index(order.status)
            if order.status in ORDER_STATUS_SEQUENCE
            else 0
        )
        status_labels = dict(Order.STATUS_CHOICES)

        timeline = []
        for i, step_status in enumerate(ORDER_STATUS_SEQUENCE):
            entry = history_by_status.get(step_status)
            timeline.append({
                'status': step_status,
                'label': status_labels.get(step_status, step_status),
                'done': i <= current_index,
                'current': i == current_index,
                'timestamp': entry.created_at if entry else None,
            })

        # How far along the green fill line should reach, as a percent
        # of the space between dot centers — e.g. 3 of 4 steps in =
        # 2/3 of the way along (dot-to-dot, not dot count), so the fill
        # visually stops exactly at the current step's dot.
        steps_count = len(ORDER_STATUS_SEQUENCE)
        timeline_fill_percent = (
            round((current_index / (steps_count - 1)) * 100)
            if steps_count > 1 else 100
        )

    return render(request, 'orders/order_detail.html', {
        'order': order,
        'timeline': timeline,
        'timeline_fill_percent': timeline_fill_percent,
        'mapbox_access_token': settings.MAPBOX_ACCESS_TOKEN,
    })


@login_required
def cancel_order(request, order_id):

    order = get_object_or_404(
        Order,
        id=order_id,
        user=request.user
    )

    if not order.can_cancel:
        messages.error(
            request,
            "This order can no longer be cancelled."
        )
        return redirect(
            "order_detail",
            order_id=order.id
        )

    if request.method == "POST":

        # `reason` is a model choice and `note` is a free-text explanation
        # that the customer only sees when "other" is picked. Both arrive
        # from a hand-built template, so they are checked here rather than
        # by a Django form.
        reason, reason_error = parse_choice(
            request.POST.get("reason"),
            "cancellation reason",
            Order.CANCEL_REASON_CHOICES,
        )

        note, note_error = parse_text(
            request.POST.get("note"),
            "Please tell us more",
            required=False,
            min_length=10,
            max_length=1000,
        )

        if reason == "other" and not note:
            note_error = (
                "Please tell us why you are cancelling your order."
            )

        errors = [error for error in (reason_error, note_error) if error]

        if errors:
            for error in errors:
                messages.error(request, error)

            # Re-render rather than redirect so the customer keeps the
            # order they were looking at instead of landing back on the
            # list with a message and no form.
            return render(
                request,
                "orders/cancel_order.html",
                {
                    "order": order,
                    "reason": request.POST.get("reason", ""),
                    "note": request.POST.get("note", ""),
                }
            )

        order.cancel_reason = reason
        order.cancel_note = note
        order.save(update_fields=['cancel_reason', 'cancel_note'])

        # Route through set_status() instead of setting order.status
        # directly — this is what actually writes a row to
        # OrderStatusHistory (and sets cancelled_at). Setting the field
        # by hand, as this used to do, silently skipped the history log,
        # which meant a cancelled order's timeline would show no record
        # of the cancellation at all.
        order.set_status('cancelled', note=note, changed_by=request.user)

        # Restore stock
        for item in order.items.all():

            product = item.product

            product.stock += item.quantity

            product.save()

        UserEvent.objects.create(
            user=request.user,
            event_type="ORDER_CANCELLED"
        )

        messages.success(
            request,
            "Your order has been cancelled successfully."
        )

        return redirect("order_list")

    return render(
        request,
        "orders/cancel_order.html",
        {
            "order": order
        }
    )


@login_required
def request_refund(request, order_id):
    order = get_object_or_404(
        Order,
        id=order_id,
        user=request.user
    )

    # Only paid orders
    if order.payment_status != "PAID":
        messages.error(request, "Only paid orders can be refunded.")
        return redirect("order_detail", order.id)

    # Already requested
    if hasattr(order, "refund_request"):
        messages.warning(request, "Refund has already been requested.")
        return redirect("order_detail", order.id)

    if request.method == "POST":
        form = RefundRequestForm(request.POST)

        if form.is_valid():

            refund = form.save(commit=False)
            refund.order = order
            refund.save()

            order.status = "cancelled"
            order.refund_status = "PENDING"
            order.payment_status = "REFUND_PENDING"
            order.save()

            messages.success(
                request,
                "Your refund request has been submitted."
            )

            return redirect("order_detail", order.id)

    else:
        form = RefundRequestForm()

    return render(
        request,
        "orders/request_refund.html",
        {
            "order": order,
            "form": form,
        },
    )


@staff_member_required
def order_list_admin(request):
    query = request.GET.get('q', '').strip()
    status = request.GET.get('status', 'all')

    orders = Order.objects.select_related('user', 'coupon').prefetch_related('items')

    if status == 'initiated':
        # Separate place for unfinished payments
        orders = orders.filter(payment_status='INITIATED')
    else:
        # All / Pending / Processing / ... never include unfinished payments
        orders = orders.exclude(payment_status='INITIATED')
        if status != 'all':
            orders = orders.filter(status=status)

    if query:
        orders = orders.filter(
            Q(id__icontains=query) |
            Q(user__username__icontains=query) |
            Q(user__email__icontains=query)
        )

    initiated_count = Order.objects.filter(payment_status='INITIATED').count()

    paginator = Paginator(orders, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'admin/order_list.html', {
        'page_obj': page_obj,
        'query': query,
        'status': status,
        'initiated_count': initiated_count,
    })


@staff_member_required
def order_detail_admin(request, pk):
    order = get_object_or_404(
        Order.objects.select_related('user').prefetch_related(
            'items', 'status_history'),
        pk=pk
    )
    return render(request, 'admin/order_detail.html', {'order': order})


@staff_member_required
def order_update_status(request, pk):
    order = get_object_or_404(Order, pk=pk)

    if request.method == "POST":

        new_status = request.POST.get("status")

        note, note_error = parse_text(
            request.POST.get("note"),
            "Note",
            required=False,
            max_length=1000,
        )

        if note_error:
            messages.error(request, note_error)
            return redirect(
                request.META.get("HTTP_REFERER", "order_list_admin")
            )

        note = note or None

        valid_statuses = [
            choice[0]
            for choice in Order.STATUS_CHOICES
            if choice[0] != "cancelled"
        ]

        if new_status in valid_statuses:

            flow = Order.STATUS_FLOW

            # Only allow moving forward
            if order.status not in flow or flow.index(new_status) <= flow.index(order.status):
                messages.error(
                    request,
                    f"Order #{order.id} is already {order.get_status_display()}. "
                    f"You can't change it back."
                )
                return redirect(
                    request.META.get("HTTP_REFERER", "order_list_admin")
                )

            order.set_status(
                new_status,
                note=note,
                changed_by=request.user
            )

            # Automatically mark COD orders as paid when delivered
            if (
                new_status == "delivered"
                and order.payment_method == "COD"
                and order.payment_status != "PAID"
            ):
                order.payment_status = "PAID"
                order.paid_at = timezone.now()
                order.save(update_fields=["payment_status", "paid_at"])

                transaction.on_commit(
                    lambda: paid_order_created.delay(order.id)
                )

                # COD is a real retention recovery only after delivery/payment.
                from apps.churn.tasks import process_retention_order_task
                transaction.on_commit(
                    lambda oid=order.id: process_retention_order_task.delay(oid)
                )

            messages.success(
                request,
                f"Order #{order.id} marked as {order.get_status_display()}."
            )

        else:
            messages.error(request, "Invalid status.")

    return redirect(
        request.META.get("HTTP_REFERER", "order_list_admin")
    )


@staff_member_required
def order_cancel(request, pk):
    order = get_object_or_404(Order, pk=pk)
    if request.method == 'POST':
        order.set_status('cancelled', note='Cancelled by admin',
                         changed_by=request.user)
        messages.success(request, f"Order #{order.id} has been cancelled.")
    return redirect(request.META.get('HTTP_REFERER', 'order_list_admin'))


@staff_member_required
def process_refund(request, pk):
    order = get_object_or_404(Order, pk=pk)

    if request.method != "POST":
        return redirect('order_list_admin')

    reference, reference_error = parse_text(
        request.POST.get("reference_id"),
        "Reference ID",
        min_length=3,
        max_length=100,
    )

    notes, notes_error = parse_text(
        request.POST.get("notes"),
        "Notes",
        required=False,
        max_length=1000,
    )

    errors = [error for error in (reference_error, notes_error) if error]

    if errors:
        for error in errors:
            messages.error(request, error)
        return redirect('order_list_admin')

    # Guard against double-processing a refund (double-click, retry, etc.)
    # — refund_order() subtracts revenue every time it's called, so this
    # must run exactly once per order.
    if order.payment_status == "REFUNDED":
        return redirect('order_list_admin')

    # NOTE: the Order model has no refund_reference / refund_notes columns,
    # so these two lines set throwaway attributes and the values are not
    # persisted. It predates the validation work and needs a decision:
    # either add the columns, or drop the inputs from the refund modal.
    # The reference does reach the customer through the notification below.
    order.refund_reference = reference
    order.refund_notes = notes
    order.payment_status = "REFUNDED"
    order.refund_status = "COMPLETED"
    order.refunded_at = timezone.now()
    order.save()

    # Only pull the order out of the revenue numbers if it had actually
    # been counted as paid revenue in the first place.
    transaction.on_commit(lambda: order_refunded.delay(order.id))

    Notification.objects.create(
        recipient=order.user,
        notif_type='REFUND',
        title='Refund processed',
        message=(
            f"Your refund of Rs. {order.total_price} for order #{order.id} "
            f"has been processed. Reference ID: {reference}."
        ),
    )

    return redirect('order_list_admin')

# ---------------------------------------------------------------------------
# COUPON
# ---------------------------------------------------------------------------

# Coupon codes end up in URLs, session keys and printed on banners, so they
# are restricted to a safe, copy-pasteable character set instead of whatever
# the admin happened to type.
COUPON_CODE_RE = re.compile(r'^[A-Z0-9_-]+$')


def validate_coupon_post(request, coupon=None):
    """
    Validate the coupon form shared by coupon_add and coupon_edit.

    Returns (values, errors). These views used to read `request.POST`
    straight into DecimalField / PositiveIntegerField / DateTimeField
    columns, so a typo in a number or a date raised ValueError inside
    `save()` and returned a 500 instead of a form error.

    `coupon` is the instance being edited, used to skip the "code already
    exists" check against the coupon's own row.
    """
    values = {}
    errors = []

    # ---------------------------------------------------------
    # CODE
    # ---------------------------------------------------------
    code, code_error = parse_text(
        request.POST.get('code', '').strip().upper(),
        'Coupon code',
        min_length=3,
        max_length=50,
    )

    if code_error:
        errors.append(code_error)
    elif not COUPON_CODE_RE.match(code):
        errors.append(
            'Coupon code can only contain letters, numbers, "-" and "_".'
        )
    else:
        duplicates = Coupon.objects.filter(code__iexact=code)

        if coupon is not None:
            duplicates = duplicates.exclude(pk=coupon.pk)

        if duplicates.exists():
            errors.append(f"A coupon with code '{code}' already exists.")
        else:
            values['code'] = code

    # ---------------------------------------------------------
    # TYPES
    # ---------------------------------------------------------
    coupon_type, type_error = parse_choice(
        request.POST.get('coupon_type') or 'STANDARD',
        'coupon type',
        Coupon.COUPON_TYPE_CHOICES,
        default='STANDARD',
    )

    if type_error:
        errors.append(type_error)
    else:
        values['coupon_type'] = coupon_type

    discount_type, discount_type_error = parse_choice(
        request.POST.get('discount_type') or 'PERCENTAGE',
        'discount type',
        Coupon.DISCOUNT_TYPE_CHOICES,
        default='PERCENTAGE',
    )

    if discount_type_error:
        errors.append(discount_type_error)
    else:
        values['discount_type'] = discount_type

    # ---------------------------------------------------------
    # DISCOUNT VALUE
    # ---------------------------------------------------------
    # Ignored for BUY_X_GET_Y (the discount comes from
    # get_discount_percent), but that column is NOT NULL, so it still has
    # to be given a number.
    needs_discount_value = coupon_type != 'BUY_X_GET_Y'

    discount_value, discount_value_error = parse_decimal(
        request.POST.get('discount_value'),
        'Discount value',
        required=needs_discount_value,
        min_value=None if needs_discount_value else 0,
        default=Decimal('0'),
    )

    if discount_value_error is None and needs_discount_value:
        if discount_value <= 0:
            discount_value_error = 'Discount value must be greater than 0.'
        elif discount_type == 'PERCENTAGE' and discount_value > 100:
            discount_value_error = (
                'A percentage discount cannot be greater than 100.'
            )

    if discount_value_error:
        errors.append(discount_value_error)
    else:
        values['discount_value'] = discount_value

    # ---------------------------------------------------------
    # MINIMUM ORDER AMOUNT
    # ---------------------------------------------------------
    min_order_amount, min_order_error = parse_decimal(
        request.POST.get('min_order_amount', '0'),
        'Minimum order amount',
        required=False,
        min_value=0,
        default=Decimal('0'),
    )

    if min_order_error:
        errors.append(min_order_error)
    else:
        values['min_order_amount'] = min_order_amount

    # ---------------------------------------------------------
    # MIN_QUANTITY
    # ---------------------------------------------------------
    min_quantity, min_quantity_error = parse_int(
        request.POST.get('min_quantity'),
        'Minimum items in cart',
        required=(coupon_type == 'MIN_QUANTITY'),
        min_value=1,
        default=None,
    )

    if min_quantity_error:
        errors.append(min_quantity_error)
    else:
        values['min_quantity'] = min_quantity

    # ---------------------------------------------------------
    # BUY X GET Y
    # ---------------------------------------------------------
    needs_buy_get = coupon_type == 'BUY_X_GET_Y'

    buy_quantity, buy_quantity_error = parse_int(
        request.POST.get('buy_quantity'),
        'Buy quantity',
        required=needs_buy_get,
        min_value=1,
        default=None,
    )

    if buy_quantity_error:
        errors.append(buy_quantity_error)
    else:
        values['buy_quantity'] = buy_quantity

    get_quantity, get_quantity_error = parse_int(
        request.POST.get('get_quantity'),
        'Get quantity',
        required=needs_buy_get,
        min_value=1,
        default=None,
    )

    if get_quantity_error:
        errors.append(get_quantity_error)
    else:
        values['get_quantity'] = get_quantity

    get_discount_percent, get_discount_error = parse_int(
        request.POST.get('get_discount_percent', '100'),
        'Discount on "get" items',
        required=False,
        min_value=1,
        max_value=100,
        default=100,
    )

    if get_discount_error:
        errors.append(get_discount_error)
    else:
        values['get_discount_percent'] = get_discount_percent

    # ---------------------------------------------------------
    # MAX USES
    # ---------------------------------------------------------
    max_uses, max_uses_error = parse_int(
        request.POST.get('max_uses'),
        'Max uses',
        required=False,
        min_value=1,
        default=None,
    )

    if max_uses_error:
        errors.append(max_uses_error)
    else:
        values['max_uses'] = max_uses

    # ---------------------------------------------------------
    # VALIDITY WINDOW
    # ---------------------------------------------------------
    valid_from, valid_from_error = parse_datetime_input(
        request.POST.get('valid_from'),
        'Valid from',
    )

    if valid_from_error:
        errors.append(valid_from_error)

    valid_until, valid_until_error = parse_datetime_input(
        request.POST.get('valid_until'),
        'Valid until',
    )

    if valid_until_error:
        errors.append(valid_until_error)

    if valid_from and valid_until and valid_until <= valid_from:
        errors.append('Valid until must be after valid from.')

    values['valid_from'] = valid_from
    values['valid_until'] = valid_until

    values['is_active'] = request.POST.get('is_active') == 'on'

    return values, errors


def unsaved_coupon_from_post(request, original=None):
    """
    Build an unsaved Coupon from the submitted values.

    coupon_edit.html reads every input from `coupon.*`, so re-rendering it
    with an unsaved instance is what keeps the admin's input on screen
    after a validation error instead of silently reverting the form. This
    view used to redirect on error, which threw the input away entirely.
    """
    coupon = Coupon(used_count=getattr(original, 'used_count', 0) or 0)

    for field in (
        'code',
        'coupon_type',
        'discount_type',
        'discount_value',
        'min_order_amount',
        'min_quantity',
        'buy_quantity',
        'get_quantity',
        'get_discount_percent',
        'max_uses',
    ):
        setattr(coupon, field, request.POST.get(field, ''))

    coupon.valid_from = request.POST.get('valid_from', '').strip() or None
    coupon.valid_until = request.POST.get('valid_until', '').strip() or None
    coupon.is_active = request.POST.get('is_active') == 'on'

    return coupon


@login_required
@staff_member_required
def coupon_list(request):
    coupons = Coupon.objects.all().order_by('-created_at')

    q = request.GET.get('q', '').strip()
    if q:
        coupons = coupons.filter(code__icontains=q)

    status = request.GET.get('status')
    now = timezone.now()
    if status == 'active':
        coupons = coupons.filter(is_active=True)
    elif status == 'inactive':
        coupons = coupons.filter(is_active=False)
    elif status == 'expired':
        coupons = coupons.filter(valid_until__lt=now)

    paginator = Paginator(coupons, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'admin/coupon_list.html', {
        'page_obj': page_obj,
        'query': q,
        'status': status or 'all',
        'now': now,
    })


@login_required
@staff_member_required
def coupon_add(request):
    if request.method == 'POST':
        values, errors = validate_coupon_post(request)

        if errors:
            for error in errors:
                messages.error(request, error)

            return render(request, 'admin/coupon_add.html', {
                'form_data': request.POST,
            })

        Coupon.objects.create(**values)

        messages.success(request, f"Coupon '{values['code']}' created.")
        return redirect('coupon_list')

    return render(request, 'admin/coupon_add.html', {'form_data': {}})


@login_required
@staff_member_required
def coupon_edit(request, pk):
    coupon = get_object_or_404(Coupon, pk=pk)

    if request.method == 'POST':
        values, errors = validate_coupon_post(request, coupon=coupon)

        if errors:
            for error in errors:
                messages.error(request, error)

            return render(request, 'admin/coupon_edit.html', {
                'coupon': unsaved_coupon_from_post(request, coupon),
            })

        for field, value in values.items():
            setattr(coupon, field, value)

        coupon.save()

        messages.success(request, f"Coupon '{coupon.code}' updated.")
        return redirect('coupon_list')

    return render(request, 'admin/coupon_edit.html', {'coupon': coupon})


@login_required
@staff_member_required
def coupon_delete_confirm(request, pk):
    coupon = get_object_or_404(Coupon, pk=pk)

    if request.method == 'POST':
        coupon.delete()
        messages.success(request, f"Coupon '{coupon.code}' deleted.")
        return redirect('coupon_list')

    return render(request, 'admin/confirm_delete.html', {
        'object': coupon,
        'object_label': coupon.code,
        'object_type': 'coupon',
        'warning': (
            f"This coupon has been used {coupon.used_count} time(s). "
            f"Deleting it won't affect past orders, but it can no longer be applied."
        ) if coupon.used_count else None,
        'cancel_link': reverse('coupon_list'),
    })