import base64
import hashlib
import hmac
import json
import uuid
from decimal import Decimal
from django.contrib.admin.views.decorators import staff_member_required
from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.http import JsonResponse
from django.urls import reverse
from django.utils import timezone
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from apps.products.models import Product
from apps.activity.models import UserEvent
from apps.addresses.models import Address
from .forms import RefundRequestForm

from .models import Cart, CartItem, Order, OrderItem, Coupon
from django.core.paginator import Paginator
from django.db.models import Q

SESSION_COUPON_KEY = 'applied_coupon_code'


def _get_session_coupon(request, order_amount):
    """
    Looks up the coupon code (if any) stored in session, re-validates it
    against the current order_amount, and returns a tuple:
        (coupon_or_None, discount_amount)

    If the stored coupon is no longer valid (expired, cart total dropped
    below min_order_amount, etc.), it is silently cleared from the session
    and (None, Decimal('0')) is returned.
    """
    code = request.session.get(SESSION_COUPON_KEY)

    if not code:
        return None, Decimal('0')

    try:
        coupon = Coupon.objects.get(code__iexact=code) # 1. does it exist?
    except Coupon.DoesNotExist:
        request.session.pop(SESSION_COUPON_KEY, None)
        return None, Decimal('0')

    is_valid, _ = coupon.is_valid(order_amount=order_amount) # 2. active? not expired? under usage limit? above min order?

    if not is_valid:
        request.session.pop(SESSION_COUPON_KEY, None) # 4. store it in session
        return None, Decimal('0')

    discount_amount = coupon.calculate_discount(order_amount) # 3. how much is the discount?
    return coupon, discount_amount


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

    is_valid, error_message = coupon.is_valid(order_amount=cart_total)

    if not is_valid:
        return JsonResponse({'success': False, 'error': error_message})

    discount_amount = coupon.calculate_discount(cart_total)
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
        return redirect('cart')
    
    if not addresses.exists():
        messages.warning(
            request,
            "Please add a delivery address first."
        )
        return redirect("addresses:add_address")

    if request.method == 'GET':
        UserEvent.objects.create(
            user=request.user,
            event_type='CHECKOUT_STARTED'
        )

    if request.method == 'POST':
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
                
                address_id = request.POST.get("address")

                if not address_id:
                    messages.error(request, "Please select a delivery address.")
                    return redirect("checkout")

                address = get_object_or_404(
                    Address,
                    id=address_id,
                    user=request.user
                )

                # Coupon (if a valid one is stored in session for this cart)
                cart_total = cart.total_price
                coupon_obj, discount_amount = _get_session_coupon(request, cart_total)
                final_total = cart_total - discount_amount

                # Create unpaid order only. Do NOT reduce stock yet.
                order = Order.objects.create(
                    user=request.user,
                    total_price=cart_total,
                    coupon=coupon_obj,
                    discount_amount=discount_amount,
                    payment_status='INITIATED',
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
                order.status_history.create(status='pending')
                
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
                
                if payment_method == "COD":

                    order.payment_status = "UNPAID"
                    order.save()

                    if order.coupon:
                        Coupon.objects.filter(pk=order.coupon_id).update(
                            used_count=F('used_count') + 1
                        )

                    request.session.pop(SESSION_COUPON_KEY, None)

                    cart.items.all().delete()

                    messages.success(
                        request,
                        "Your order has been placed successfully."
                    )

                    return redirect("order_detail", order.id)

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

                # Coupon is now snapshotted on the order; used_count is
                # incremented only once payment is confirmed (esewa_success).
                request.session.pop(SESSION_COUPON_KEY, None)

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

    # GET: show current coupon state (if any) alongside cart/addresses
    cart_total = cart.total_price
    applied_coupon, discount_amount = _get_session_coupon(request, cart_total)
    final_total = cart_total - discount_amount

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
        }
    )


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

            # Coupon usage is only counted once payment is confirmed,
            # so failed/abandoned checkouts never consume a redemption.
            if order.coupon:
                Coupon.objects.filter(pk=order.coupon_id).update(
                    used_count=F('used_count') + 1
                )

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
        # payment_status__in=[
        #     "PAID",
        #     "REFUND_PENDING",
        #     "REFUNDED",
        # ]
    ).prefetch_related("items").order_by("-created_at")

    return render(request, 'orders/order_list.html', {
        'orders': orders
    })


@login_required
def order_detail(request, order_id):
    order = get_object_or_404(
        Order,
        id=order_id,
        user=request.user,
        # payment_status='PAID'
    )

    return render(request, 'orders/order_detail.html', {
        'order': order
    })


# @login_required
# def cancel_order(request, order_id):
#     order = get_object_or_404(
#         Order,
#         id=order_id,
#         user=request.user,
#         payment_status='PAID'
#     )

#     if order.status in ['pending', 'processing']:
#         order.status = 'cancelled'
#         order.save()

#         UserEvent.objects.create(
#             user=request.user,
#             event_type='ORDER_CANCELLED'
#         )

#         messages.success(
#             request,
#             f"Order #{order.id} cancelled successfully."
#         )
#     else:
#         messages.warning(
#             request,
#             "This order cannot be cancelled."
#         )

#     return redirect(
#         'order_detail',
#         order_id=order.id
#     )

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
        
    if order.payment_method == "COD":
        order.payment_status = "UNPAID"
        
    if (
        order.payment_method == "ESEWA"
        and order.payment_status == "PAID"
    ):
        order.payment_status = "REFUND_PENDING"

    if request.method == "POST":

        reason = request.POST.get("reason")
        note = request.POST.get("note")

        order.status = "cancelled"
        order.cancel_reason = reason
        order.cancel_note = note
        order.cancelled_at = timezone.now()
        order.save()

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
 
    orders = Order.objects.select_related('user').prefetch_related('items')
 
    if status != 'all':
        orders = orders.filter(status=status)
 
    if query:
        orders = orders.filter(
            Q(id__icontains=query) |
            Q(user__username__icontains=query) |
            Q(user__email__icontains=query)
        )
 
    paginator = Paginator(orders, 20)
    page_obj = paginator.get_page(request.GET.get('page'))
 
    return render(request, 'admin/order_list.html', {
        'page_obj': page_obj,
        'query': query,
        'status': status,
    })
 
 
@staff_member_required
def order_detail_admin(request, pk):
    order = get_object_or_404(
        Order.objects.select_related('user').prefetch_related('items', 'status_history'),
        pk=pk
    )
    return render(request, 'admin/order_detail.html', {'order': order})
 
 
@staff_member_required
def order_update_status(request, pk):
    order = get_object_or_404(Order, pk=pk)
    if request.method == 'POST':
        new_status = request.POST.get('status')
        note = request.POST.get('note', '').strip() or None
        valid_statuses = [choice[0] for choice in Order.STATUS_CHOICES if choice[0] != 'cancelled']
        if new_status in valid_statuses:
            order.set_status(new_status, note=note, changed_by=request.user)
            messages.success(request, f"Order #{order.id} marked as {order.get_status_display()}.")
        else:
            messages.error(request, "Invalid status.")
    return redirect(request.META.get('HTTP_REFERER', 'order_list_admin'))
 
 
@staff_member_required
def order_cancel(request, pk):
    order = get_object_or_404(Order, pk=pk)
    if request.method == 'POST':
        order.set_status('cancelled', note='Cancelled by admin', changed_by=request.user)
        messages.success(request, f"Order #{order.id} has been cancelled.")
    return redirect(request.META.get('HTTP_REFERER', 'order_list_admin'))