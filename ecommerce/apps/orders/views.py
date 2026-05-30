from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from apps.products.models import Product
from .models import Cart, CartItem, Order, OrderItem
from .models import Order

@login_required
# Views for handling cart and order operations, including viewing the cart, adding/removing items, checking out, and viewing order history and details.
def cart_view(request):
    cart, _ = Cart.objects.get_or_create(user=request.user)
    return render(request, 'orders/cart.html', {'cart': cart})

@login_required
# View to add a product to the user's cart. It checks if the product exists and is active, then either creates a new cart item or updates the quantity if it already exists. It also provides feedback messages to the user and redirects back to the cart view.
def add_to_cart(request, product_id):
    product = get_object_or_404(Product, id=product_id, is_active=True)
    cart, _ = Cart.objects.get_or_create(user=request.user)
    item, created = CartItem.objects.get_or_create(cart=cart, product=product)
    if not created:
        item.quantity += 1
        item.save()
    messages.success(request, f"'{product.name}' added to cart.")
    return redirect('cart')

@login_required
# View to remove an item from the user's cart. It checks if the cart item exists for the given item ID and belongs to the user's cart, then deletes it and provides feedback messages before redirecting back to the cart view.
def remove_from_cart(request, item_id):
    item = get_object_or_404(CartItem, id=item_id, cart__user=request.user)
    item.delete()
    messages.info(request, "Item removed from cart.")
    return redirect('cart')

@login_required
# View for the checkout process. It retrieves the user's cart and checks if it has items. If the cart is empty, it displays a warning and redirects to the cart view. If the cart has items, it processes the order creation and clears the cart after successful placement. It also provides feedback messages and redirects to the order detail view for the newly created order.
def checkout_view(request):
    cart, _ = Cart.objects.get_or_create(user=request.user)
    if not cart.items.exists():
        messages.warning(request, "Your cart is empty.")
        return redirect('cart')

    if request.method == 'POST':
        # Create the Order
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
        cart.items.all().delete()   # clear cart after order
        messages.success(request, f"Order #{order.id} placed successfully!")
        return redirect('order_detail', order_id=order.id)

    return render(request, 'orders/checkout.html', {'cart': cart})

@login_required
def order_list(request):
    orders = Order.objects.filter(user=request.user).order_by('-created_at')

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