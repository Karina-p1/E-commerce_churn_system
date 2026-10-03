from datetime import timedelta
from decimal import Decimal, InvalidOperation
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, ProtectedError
from django.db.models import Count, Avg
from django.urls import reverse
from django.utils import timezone
from django.core.paginator import Paginator
from apps.accounts.models import User
from django.http import JsonResponse

from apps.products.models import Category, Brand, Product, Review, Wishlist
from apps.analytics.services import get_top_products
from apps.activity.models import UserEvent

from apps.orders.models import Order, OrderItem
from apps.loyalty.services import LoyaltyService
from ecommerce.validators import (
    MAX_IMAGE_BYTES,
    parse_choice,
    parse_datetime_input,
    parse_decimal,
    parse_image,
    parse_int,
    parse_text,
)

# Admin uploads. 5 MB is generous for a product photo and small enough
# that a fat-fingered 40 MP phone shot can't quietly fill the media root.
MAX_UPLOAD_IMAGE_BYTES = MAX_IMAGE_BYTES

def view_products(request):
    categories = Category.objects.all()
    top_products = get_top_products(limit=10)

    # Brand strip — ordered by admin-set priority number, then alphabetically as tiebreaker
    brands = Brand.objects.all().order_by('order', 'name')

    products = Product.objects.filter(
        is_active=True
    ).select_related(
        'category',
        'brand'
    )

    # Special offers: active, in stock, and at least 20% off.
    all_active_products = Product.objects.filter(
        is_active=True,
        stock__gt=0
    ).select_related(
        'category',
        'brand'
    )

    special_offers = [
        product
        for product in all_active_products
        if product.is_offer_active and product.discount_percent >= 20
    ]

    # Brand
    brand_slug = request.GET.get('brand', '').strip()
    if brand_slug:
        products = products.filter(brand__slug=brand_slug)

    # Category
    category_slug = request.GET.get('category', '').strip()
    if category_slug:
        products = products.filter(category__slug=category_slug)

    # Search
    q = request.GET.get('q', '').strip()
    if q:
        products = products.filter(
            Q(name__icontains=q) |
            Q(description__icontains=q) |
            Q(brand__name__icontains=q) |
            Q(category__name__icontains=q)
        )

    # Price range uses the stored/base price because effective_price is a Python property.
    min_price = request.GET.get('min_price', '').strip()
    max_price = request.GET.get('max_price', '').strip()

    if min_price:
        try:
            products = products.filter(price__gte=Decimal(min_price))
        except (InvalidOperation, ValueError):
            min_price = ''

    if max_price:
        try:
            products = products.filter(price__lte=Decimal(max_price))
        except (InvalidOperation, ValueError):
            max_price = ''

    # Rating
    min_rating = request.GET.get('min_rating', '').strip()
    sort = request.GET.get('sort', '').strip()

    # Annotate once when either rating filtering or rating sorting needs it.
    if min_rating or sort == 'rating':
        products = products.annotate(
            avg_rating=Avg('reviews__rating')
        )

    if min_rating:
        try:
            products = products.filter(avg_rating__gte=float(min_rating))
        except ValueError:
            min_rating = ''

    # Availability
    stock = request.GET.get('stock', '').strip()
    if stock == 'in':
        products = products.filter(stock__gt=0)

    # Active discounted products
    discounted = request.GET.get('discounted', '').strip()
    if discounted == '1':
        now = timezone.now()
        products = products.filter(
            discount_percentage__gt=0
        ).filter(
            Q(offer_start__isnull=True) | Q(offer_start__lte=now)
        ).filter(
            Q(offer_end__isnull=True) | Q(offer_end__gte=now)
        )

    # Single sorting control: the sidebar dropdown.
    if sort == 'price_low':
        products = products.order_by('price', 'name')
    elif sort == 'price_high':
        products = products.order_by('-price', 'name')
    elif sort == 'rating':
        products = products.order_by('-avg_rating', 'name')
    elif sort == 'newest':
        products = products.order_by('-created_at')
    else:
        products = products.order_by('-created_at')

    # Wishlist IDs for current user
    wishlist_ids = set()
    if request.user.is_authenticated:
        wishlist_ids = set(
            Wishlist.objects.filter(
                user=request.user
            ).values_list('product_id', flat=True)
        )

    return render(request, "products/dashboard.html", {
        "products": products,
        "special_offers": special_offers,
        "top_products": top_products,
        "all_brands": brands,
        "all_categories": categories,
        "active_brand": brand_slug,
        "active_category": category_slug,
        "wishlist_ids": wishlist_ids,
        "min_price": min_price,
        "max_price": max_price,
        "min_rating": min_rating,
    })

def build_stars(rating):
    return [i < round(rating) for i in range(5)]


def product_detail(request, slug):
    product = get_object_or_404(Product, slug=slug, is_active=True)

    if request.user.is_authenticated:
        recent_view_exists = UserEvent.objects.filter(
            user=request.user,
            product=product,
            event_type='VIEW',
            created_at__gte=timezone.now() - timedelta(minutes=5)
        ).exists()

        if not recent_view_exists:
            UserEvent.objects.create(
                user=request.user,
                product=product,
                event_type='VIEW'
            )

    reviews_qs = product.reviews.select_related('customer').order_by('-created_at')
    total = reviews_qs.count()

    # Clear reviews_qs ordering before grouping by rating.
    # Otherwise the queryset's `-created_at` ordering can leak into the
    # GROUP BY, producing multiple rows for the same star value. Converting
    # those rows to a dict then overwrites duplicate ratings and makes the
    # distribution counts/bars incorrect.
    dist_raw = (
        reviews_qs
        .order_by()
        .values('rating')
        .annotate(count=Count('id'))
        .order_by('rating')
    )
    dist_map = {d['rating']: d['count'] for d in dist_raw}

    rating_distribution = [
        {
            'label': star,
            'count': dist_map.get(star, 0),
            'pct': round(dist_map.get(star, 0) / total * 100) if total else 0,
        }
        for star in range(5, 0, -1)
    ]

    product_stars = build_stars(product.rating)
    review_stars = {review.id: build_stars(review.rating) for review in reviews_qs}

    return render(request, 'products/product_detail.html', {
        'product': product,
        'reviews': reviews_qs,
        'rating_distribution': rating_distribution,
        'product_stars': product_stars,
        'review_stars': review_stars,
    })

@login_required
def post_review(request, slug):
    product = get_object_or_404(
        Product,
        slug=slug,
        is_active=True
    )

    if request.method == 'POST':

        # Prevent duplicate reviews
        if Review.objects.filter(
            product=product,
            customer=request.user
        ).exists():
            messages.warning(
                request,
                'You have already reviewed this product.'
            )
            return redirect(
                'products:product_detail',
                slug=slug
            )

        rating = request.POST.get('rating')
        comment, comment_error = parse_text(
            request.POST.get('comment'),
            'Review',
            min_length=10,
            max_length=2000,
        )

        if not rating or comment_error:
            messages.error(
                request,
                comment_error
                or 'Please provide both a rating and a comment.'
            )
            return redirect(
                'products:product_detail',
                slug=slug
            )

        try:
            rating = int(rating)
        except ValueError:
            messages.error(
                request,
                'Invalid rating value.'
            )
            return redirect(
                'products:product_detail',
                slug=slug
            )

        if not (1 <= rating <= 5):
            messages.error(
                request,
                'Rating must be between 1 and 5.'
            )
            return redirect(
                'products:product_detail',
                slug=slug
            )

        # Create the review
        Review.objects.create(
            product=product,
            customer=request.user,
            rating=rating,
            comment=comment
        )

        # Log review activity for churn/behavior analysis
        UserEvent.objects.create(
            user=request.user,
            product=product,
            event_type='REVIEW'
        )

        # --------------------------------------------------
        # LOYALTY: Verified Purchase Review Reward
        # --------------------------------------------------
        qualifying_order = (
            Order.objects
            .filter(
                user=request.user,
                payment_status='PAID',
                items__product=product,
            )
            .order_by('-paid_at', '-id')
            .first()
        )

        if qualifying_order:
            try:
                LoyaltyService.award_review_points(
                    user=request.user,
                    order=qualifying_order,
                    product=product,
                )

                messages.success(
                    request,
                    'Your review has been posted and you earned 50 loyalty points!'
                )

            except ValueError as e:
                messages.warning(
                    request,
                    f'Your review has been posted, but loyalty points were not awarded: {e}'
                )
        else:
            messages.success(
                request,
                'Your review has been posted.'
            )

    return redirect(
        'products:product_detail',
        slug=slug
    )


@login_required
def add_to_wishlist(request, product_id):
    product = get_object_or_404(Product, id=product_id, is_active=True)

    wishlist_item = Wishlist.objects.filter(user=request.user, product=product).first()

    if wishlist_item:
        wishlist_item.delete()
        UserEvent.objects.create(user=request.user, product=product, event_type='REMOVE_WISHLIST')
        messages.info(request, f"'{product.name}' removed from wishlist.")
    else:
        Wishlist.objects.create(user=request.user, product=product)
        UserEvent.objects.create(user=request.user, product=product, event_type='WISHLIST')
        messages.success(request, f"'{product.name}' added to wishlist ❤️")

    return redirect(request.META.get('HTTP_REFERER', 'products:view_products'))


@login_required
def wishlist_view(request):
    items = Wishlist.objects.filter(user=request.user).select_related('product')
    return render(request, 'products/wishlist.html', {'items': items})


@login_required
def remove_from_wishlist(request, product_id):
    wishlist_item = Wishlist.objects.filter(
        user=request.user,
        product_id=product_id
    ).select_related('product').first()

    if wishlist_item:
        product = wishlist_item.product
        wishlist_item.delete()
        UserEvent.objects.create(user=request.user, product=product, event_type='REMOVE_WISHLIST')
        messages.info(request, f"'{product.name}' removed from wishlist.")
    else:
        messages.warning(request, "This product was not in your wishlist.")

    return redirect('products:wishlist')


def top_products(request):
    today = timezone.now()
    month_start = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    top = (
        Product.objects
        .filter(is_active=True)
        .annotate(
            order_count=Count(
                'activity_events',
                filter=Q(
                    activity_events__event_type='ORDER',
                    activity_events__created_at__gte=month_start,
                )
            ),
            wishlist_count=Count(
                'activity_events',
                filter=Q(
                    activity_events__event_type='WISHLIST',
                    activity_events__created_at__gte=month_start,
                )
            ),
            view_count=Count(
                'activity_events',
                filter=Q(
                    activity_events__event_type='VIEW',
                    activity_events__created_at__gte=month_start,
                )
            ),
        )
        .select_related('category', 'brand')
        .order_by('-order_count', '-wishlist_count', '-view_count')[:5]
    )

    data = [
        {
            'name':           p.name,
            'category':       p.category.name if p.category else 'Uncategorized',
            'brand':          p.brand.name if p.brand else '',
            'rating':         float(p.rating) if p.rating else 0,
            'order_count':    p.order_count,
            'wishlist_count': p.wishlist_count,
            'view_count':     p.view_count,
        }
        for p in top
    ]

    return JsonResponse(data, safe=False)


# ---------------------------------------------------------------------------
# CATEGORY
# ---------------------------------------------------------------------------

@login_required
@staff_member_required
def category_list(request):
    categories = Category.objects.annotate(
        product_count=Count('products')
    ).order_by('name')

    q = request.GET.get('q', '').strip()
    if q:
        categories = categories.filter(name__icontains=q)

    paginator = Paginator(categories, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'products/category_list.html', {
        'page_obj': page_obj,
        'query': q,
    })


@login_required
@staff_member_required
def category_edit(request, pk):
    category = get_object_or_404(Category, pk=pk)

    if request.method == 'POST':
        name, name_error = parse_text(
            request.POST.get('name'),
            'Category name',
            min_length=2,
            max_length=100,
        )

        description, description_error = parse_text(
            request.POST.get('description'),
            'Description',
            required=False,
            max_length=2000,
        )

        image, image_error = parse_image(
            request.FILES.get('image'),
            'Category image',
            MAX_UPLOAD_IMAGE_BYTES,
        )

        errors = [
            error
            for error in (name_error, description_error, image_error)
            if error
        ]

        if not errors and Category.objects.filter(
            name__iexact=name
        ).exclude(pk=category.pk).exists():
            errors.append(f"A category named '{name}' already exists.")

        if errors:
            for error in errors:
                messages.error(request, error)

            # Re-render instead of redirecting so the admin's typing isn't
            # thrown away.
            return render(request, 'products/category_edit.html', {
                'category': unsaved_category_from_post(request, category),
            })

        category.name = name
        category.description = description

        if image:
            category.image = image

        category.save()

        messages.success(request, f"'{category.name}' updated.")
        return redirect('products:category_list')

    return render(request, 'products/category_edit.html', {'category': category})


@login_required
@staff_member_required
def category_delete_confirm(request, pk):
    category      = get_object_or_404(Category, pk=pk)
    product_count = category.products.count()

    if request.method == 'POST':
        try:
            category.delete()
            messages.success(request, f"'{category.name}' deleted.")
        except ProtectedError:
            messages.error(
                request,
                f"Can't delete '{category.name}' — it still has linked products."
            )
        return redirect('products:category_list')

    return render(request, 'products/confirm_delete.html', {
        'object':       category,
        'object_label': category.name,
        'object_type':  'category',
        'warning': (
            f"This category has {product_count} product(s) attached. "
            f"Deleting it will cascade-delete those products."
        ) if product_count else None,
        'cancel_link': reverse('products:category_list'),
    })


# ---------------------------------------------------------------------------
# BRAND
# ---------------------------------------------------------------------------

@login_required
@staff_member_required
def brand_list(request):
    # Admin list — ordered by priority number so admin sees the same order as the strip
    brands = Brand.objects.annotate(
        product_count=Count('products')
    ).order_by('order', 'name')

    q = request.GET.get('q', '').strip()
    if q:
        brands = brands.filter(name__icontains=q)

    paginator = Paginator(brands, 20)
    page_obj  = paginator.get_page(request.GET.get('page'))

    return render(request, 'products/brand_list.html', {
        'page_obj': page_obj,
        'query':    q,
    })


@login_required
@staff_member_required
def brand_edit(request, pk):
    brand = get_object_or_404(Brand, pk=pk)

    if request.method == 'POST':
        name, name_error = parse_text(
            request.POST.get('name'),
            'Brand name',
            min_length=2,
            max_length=100,
        )

        description, description_error = parse_text(
            request.POST.get('description'),
            'Description',
            required=False,
            max_length=2000,
        )

        order, order_error = parse_int(
            request.POST.get('order', '0'),
            'Display order',
            required=False,
            min_value=0,
            max_value=9999,
            default=0,
        )

        logo, logo_error = parse_image(
            request.FILES.get('logo'),
            'Brand logo',
            MAX_UPLOAD_IMAGE_BYTES,
        )

        errors = [
            error
            for error in (
                name_error,
                description_error,
                order_error,
                logo_error,
            )
            if error
        ]

        if not errors and Brand.objects.filter(
            name__iexact=name
        ).exclude(pk=brand.pk).exists():
            errors.append(f"A brand named '{name}' already exists.")

        if errors:
            for error in errors:
                messages.error(request, error)

            # Re-render instead of redirecting so the admin's typing isn't
            # thrown away, and hand the form the values it can still show.
            return render(request, 'products/brand_edit.html', {
                'brand': unsaved_brand_from_post(request, brand),
            })

        brand.name = name
        brand.description = description
        brand.order = order

        if logo:
            brand.logo = logo

        brand.save()

        messages.success(request, f"'{brand.name}' updated.")
        return redirect('products:brand_list')

    return render(request, 'products/brand_edit.html', {'brand': brand})


@login_required
@staff_member_required
def brand_delete_confirm(request, pk):
    brand         = get_object_or_404(Brand, pk=pk)
    product_count = brand.products.count()

    if request.method == 'POST':
        brand.delete()
        messages.success(request, f"'{brand.name}' deleted.")
        return redirect('products:brand_list')

    return render(request, 'products/confirm_delete.html', {
        'object':       brand,
        'object_label': brand.name,
        'object_type':  'brand',
        'warning': (
            f"{product_count} product(s) use this brand. They will be "
            f"kept, but their brand will be cleared."
        ) if product_count else None,
        'cancel_link': reverse('products:brand_list'),
    })


# ---------------------------------------------------------------------------
# PRODUCT
# ---------------------------------------------------------------------------


def parse_offer_datetime(value):
    """
    Parses a datetime-local input value ('YYYY-MM-DDTHH:MM') into an
    aware datetime, or returns None if empty/invalid.
    """
    parsed, error = parse_datetime_input(value, 'Offer date')

    return parsed


def unsaved_category_from_post(request, original):
    """
    An unsaved Category carrying the submitted values, so
    category_edit.html can re-render the admin's input after a validation
    error.
    """
    category = Category(pk=original.pk, image=original.image)

    category.name = (request.POST.get('name') or '').strip() or None
    category.description = (
        request.POST.get('description') or ''
    ).strip() or None

    return category


def is_pk(value):
    """
    True when `value` can be used in a `pk=` lookup.

    `Category.objects.filter(pk="abc")` raises ValueError instead of
    returning nothing, so a hand-edited or tampered form would 500 rather
    than report a validation error.
    """
    try:
        int(value)
    except (TypeError, ValueError):
        return False

    return True


def unsaved_brand_from_post(request, original):
    """
    An unsaved Brand carrying the submitted values, so brand_edit.html can
    re-render the admin's input after a validation error.
    """
    brand = Brand(pk=original.pk, logo=original.logo)

    brand.name = (request.POST.get('name') or '').strip() or None
    brand.description = (
        request.POST.get('description') or ''
    ).strip() or None

    try:
        brand.order = int((request.POST.get('order') or '').strip() or 0)
    except ValueError:
        brand.order = 0

    return brand


def validate_product_post(request):
    """
    Validate the product form shared by product_add and product_edit.

    Returns (values, errors). The gaps this closes are the ones that used
    to surface as a 500 rather than a message: a negative price, a negative
    stock count, and a category/brand id that doesn't exist (the FK is NOT
    NULL, so a bogus id failed on save).
    """
    values = {}
    errors = []

    name, name_error = parse_text(
        request.POST.get('name'),
        'Product name',
        min_length=2,
        max_length=255,
    )

    if name_error:
        errors.append(name_error)
    else:
        values['name'] = name

    description, description_error = parse_text(
        request.POST.get('description'),
        'Description',
        min_length=10,
        max_length=10000,
    )

    if description_error:
        errors.append(description_error)
    else:
        values['description'] = description

    # ---------------------------------------------------------
    # PRICE
    # ---------------------------------------------------------
    # A zero or negative price is not a discount, it is a free product.
    price, price_error = parse_decimal(
        request.POST.get('price'),
        'Price',
        default=None,
    )

    if price_error is None and price is not None and price <= 0:
        price_error = 'Price must be greater than 0.'

    if price_error:
        errors.append(price_error)
    else:
        values['price'] = price

    # ---------------------------------------------------------
    # DISCOUNT / OFFER WINDOW
    # ---------------------------------------------------------
    discount_percentage, discount_error = parse_int(
        request.POST.get('discount_percentage', '0'),
        'Discount percentage',
        required=False,
        min_value=0,
        max_value=100,
        default=0,
    )

    if discount_error:
        errors.append(discount_error)
    else:
        values['discount_percentage'] = discount_percentage

    offer_start, offer_start_error = parse_datetime_input(
        request.POST.get('offer_start'),
        'Offer start date',
    )

    if offer_start_error:
        errors.append(offer_start_error)

    offer_end, offer_end_error = parse_datetime_input(
        request.POST.get('offer_end'),
        'Offer end date',
    )

    if offer_end_error:
        errors.append(offer_end_error)

    if offer_start and offer_end and offer_end <= offer_start:
        errors.append('Offer end must be after offer start.')

    values['offer_start'] = offer_start
    values['offer_end'] = offer_end

    # ---------------------------------------------------------
    # STOCK
    # ---------------------------------------------------------
    stock, stock_error = parse_int(
        request.POST.get('stock'),
        'Stock',
        min_value=0,
        default=0,
    )

    if stock_error:
        errors.append(stock_error)
    else:
        values['stock'] = stock

    # ---------------------------------------------------------
    # CATEGORY / BRAND
    # ---------------------------------------------------------
    category_id = (request.POST.get('category') or '').strip()

    if not category_id:
        errors.append('Category is required.')
    elif not is_pk(category_id):
        errors.append('Category is required.')
    elif not Category.objects.filter(pk=category_id).exists():
        errors.append('The selected category does not exist.')
    else:
        values['category_id'] = category_id

    brand_id = (request.POST.get('brand') or '').strip()

    if brand_id and not is_pk(brand_id):
        errors.append('The selected brand does not exist.')
    elif brand_id and not Brand.objects.filter(pk=brand_id).exists():
        errors.append('The selected brand does not exist.')
    else:
        values['brand_id'] = brand_id or None

    # ---------------------------------------------------------
    # IMAGE
    # ---------------------------------------------------------
    image, image_error = parse_image(
        request.FILES.get('image'),
        'Product image',
        MAX_UPLOAD_IMAGE_BYTES,
    )

    if image_error:
        errors.append(image_error)
    elif image is not None:
        values['image'] = image

    values['is_active'] = request.POST.get('is_active') == 'on'

    return values, errors


def product_form_preview(request, product):
    """
    Reflect submitted values back onto `product` without saving, so
    product_edit.html re-renders with the admin's input instead of the
    stored row. The existing image is left in place so the preview <img>
    still resolves.

    The numbers are coerced back to Decimal/int, not left as the raw POST
    strings: the template calls `product.effective_price`, which does
    `self.price * (Decimal("1") - discount)`. That raises TypeError on a
    string, so a string would 500 the very page the error message is
    supposed to appear on.
    """
    preview = product

    preview.name = (request.POST.get('name') or '').strip() or None
    preview.description = (request.POST.get('description') or '').strip() or None

    try:
        preview.price = Decimal(
            (request.POST.get('price') or '').strip() or "0"
        )
    except (InvalidOperation, ValueError):
        preview.price = Decimal("0")

    try:
        preview.discount_percentage = int(
            (request.POST.get('discount_percentage') or '').strip() or 0
        )
    except ValueError:
        preview.discount_percentage = 0

    try:
        preview.stock = int((request.POST.get('stock') or '').strip() or 0)
    except ValueError:
        preview.stock = 0

    offer_start, _ = parse_datetime_input(
        request.POST.get('offer_start'),
        'Offer start date',
    )
    offer_end, _ = parse_datetime_input(
        request.POST.get('offer_end'),
        'Offer end date',
    )

    preview.offer_start = offer_start
    preview.offer_end = offer_end
    preview.is_active = request.POST.get('is_active') == 'on'

    return preview

@login_required
@staff_member_required
def product_list(request):
    now = timezone.now()

    products = Product.objects.select_related(
        'category', 'brand'
    ).order_by('-created_at')

    q = request.GET.get('q', '').strip()
    if q:
        products = products.filter(name__icontains=q)

    status = request.GET.get('status')
    if status == 'active':
        products = products.filter(is_active=True)
    elif status == 'inactive':
        products = products.filter(is_active=False)
    elif status == 'out_of_stock':
        products = products.filter(stock=0)
    elif status == 'on_discount':
        products = products.filter(
            discount_percentage__gt=0
        ).filter(
            Q(offer_start__isnull=True) | Q(offer_start__lte=now)
        ).filter(
            Q(offer_end__isnull=True) | Q(offer_end__gte=now)
        )

    paginator = Paginator(products, 20)
    page_obj  = paginator.get_page(request.GET.get('page'))

    return render(request, 'products/product_list.html', {
        'page_obj': page_obj,
        'query':    q,
        'status':   status or 'all',
    })


@login_required
@staff_member_required
def product_edit(request, pk):
    product    = get_object_or_404(Product, pk=pk)
    categories = Category.objects.order_by('name')
    brands     = Brand.objects.order_by('order', 'name')

    if request.method == 'POST':
        values, errors = validate_product_post(request)

        if errors:
            for error in errors:
                messages.error(request, error)

            return render(request, 'products/product_edit.html', {
                'product':    product_form_preview(request, product),
                'categories': categories,
                'brands':     brands,
                'form_data':  request.POST,
            })

        for field, value in values.items():
            setattr(product, field, value)

        product.save()

        messages.success(request, f"'{product.name}' updated.")
        return redirect('products:product_list')

    return render(request, 'products/product_edit.html', {
        'product':    product,
        'categories': categories,
        'brands':     brands,
    })


@login_required
@staff_member_required
def product_delete_confirm(request, pk):
    product = get_object_or_404(Product, pk=pk)

    if request.method == 'POST':
        product.delete()
        messages.success(request, f"'{product.name}' deleted.")
        return redirect('products:product_list')

    return render(request, 'products/confirm_delete.html', {
        'object':       product,
        'object_label': product.name,
        'object_type':  'product',
        'warning':      None,
        'cancel_link':  reverse('products:product_list'),
    })


# ---------------------------------------------------------------------------
# USERS
# ---------------------------------------------------------------------------

@login_required
@staff_member_required
def user_list(request):
    users = User.objects.all().order_by('-date_joined')

    q = request.GET.get('q', '').strip()
    if q:
        users = users.filter(username__icontains=q) | users.filter(email__icontains=q)

    status = request.GET.get('status')
    if status == 'active':
        users = users.filter(is_active=True)
    elif status == 'inactive':
        users = users.filter(is_active=False)

    paginator = Paginator(users, 20)
    page_obj  = paginator.get_page(request.GET.get('page'))

    return render(request, 'products/user_list.html', {
        'page_obj': page_obj,
        'query':    q,
        'status':   status or 'all',
    })


@login_required
@staff_member_required
def user_toggle_active(request, pk):
    user = get_object_or_404(User, pk=pk)

    if user == request.user:
        messages.error(request, "You can't deactivate your own account.")
        return redirect('products:user_list')

    user.is_active = not user.is_active
    user.save(update_fields=['is_active'])

    state = 'activated' if user.is_active else 'deactivated'
    messages.success(request, f"'{user.username}' {state}.")
    return redirect('products:user_list')


@login_required
@staff_member_required
def user_delete_confirm(request, pk):
    user = get_object_or_404(User, pk=pk)

    if user == request.user:
        messages.error(request, "You can't delete your own account.")
        return redirect('products:user_list')

    if request.method == 'POST':
        username = user.username
        user.delete()
        messages.success(request, f"'{username}' deleted.")
        return redirect('products:user_list')

    return render(request, 'products/confirm_delete.html', {
        'object':       user,
        'object_label': user.username,
        'object_type':  'user',
        'warning': (
            "This permanently deletes the account and anonymizes/cascades "
            "related orders and reviews depending on your model's on_delete "
            "settings. Consider deactivating instead if you're unsure."
        ),
        'cancel_link': reverse('products:user_list'),
    })


# ---------------------------------------------------------------------------
# ADD (CREATE) VIEWS
# ---------------------------------------------------------------------------

@login_required
@staff_member_required
def category_add(request):
    if request.method == 'POST':
        name, name_error = parse_text(
            request.POST.get('name'),
            'Category name',
            min_length=2,
            max_length=100,
        )

        description, description_error = parse_text(
            request.POST.get('description'),
            'Description',
            required=False,
            max_length=2000,
        )

        image, image_error = parse_image(
            request.FILES.get('image'),
            'Category image',
            MAX_UPLOAD_IMAGE_BYTES,
        )

        errors = [
            error
            for error in (name_error, description_error, image_error)
            if error
        ]

        if not errors and Category.objects.filter(name__iexact=name).exists():
            errors.append(f"A category named '{name}' already exists.")

        if errors:
            for error in errors:
                messages.error(request, error)
            return render(request, 'products/category_add.html', {
                'form_data': request.POST,
            })

        category = Category.objects.create(
            name=name,
            description=description,
        )

        if image:
            category.image = image
            category.save()

        messages.success(request, f"'{category.name}' created.")
        return redirect('products:category_list')

    return render(request, 'products/category_add.html', {'form_data': {}})


@login_required
@staff_member_required
def brand_add(request):
    if request.method == 'POST':
        name, name_error = parse_text(
            request.POST.get('name'),
            'Brand name',
            min_length=2,
            max_length=100,
        )

        description, description_error = parse_text(
            request.POST.get('description'),
            'Description',
            required=False,
            max_length=2000,
        )

        order, order_error = parse_int(
            request.POST.get('order', '0'),
            'Display order',
            required=False,
            min_value=0,
            max_value=9999,
            default=0,
        )

        logo, logo_error = parse_image(
            request.FILES.get('logo'),
            'Brand logo',
            MAX_UPLOAD_IMAGE_BYTES,
        )

        errors = [
            error
            for error in (
                name_error,
                description_error,
                order_error,
                logo_error,
            )
            if error
        ]

        if not errors and Brand.objects.filter(name__iexact=name).exists():
            errors.append(f"A brand named '{name}' already exists.")

        if errors:
            for error in errors:
                messages.error(request, error)
            return render(request, 'products/brand_add.html', {
                'form_data': request.POST,
            })

        brand = Brand.objects.create(
            name=name,
            description=description,
            order=order,
        )

        if logo:
            brand.logo = logo
            brand.save()

        messages.success(request, f"'{brand.name}' created.")
        return redirect('products:brand_list')

    return render(request, 'products/brand_add.html', {'form_data': {}})


@login_required
@staff_member_required
def product_add(request):
    categories = Category.objects.order_by('name')
    brands     = Brand.objects.order_by('order', 'name')

    if request.method == 'POST':
        values, errors = validate_product_post(request)

        if errors:
            for error in errors:
                messages.error(request, error)

            return render(request, 'products/product_add.html', {
                'categories': categories,
                'brands':     brands,
                'form_data':  request.POST,
            })

        product = Product.objects.create(**values)

        messages.success(request, f"'{product.name}' created.")
        return redirect('products:product_list')

    return render(request, 'products/product_add.html', {
        'categories': categories,
        'brands':     brands,
        'form_data':  {},
    })


# ---------------------------------------------------------------------------
# SEARCH AUTOCOMPLETE
# ---------------------------------------------------------------------------

def search_autocomplete(request):
    q = request.GET.get('q', '').strip()
    if len(q) < 1:
        return JsonResponse({'results': []})

    products = Product.objects.filter(
        name__istartswith=q,
        is_active=True
    ).values('name', 'slug')[:8]

    return JsonResponse({'results': list(products)})