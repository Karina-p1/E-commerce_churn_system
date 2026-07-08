from datetime import timedelta
from django.contrib.admin.views.decorators import staff_member_required

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, ProtectedError
from django.db.models import Count
from django.urls import reverse
from django.utils import timezone
from django.core.paginator import Paginator
from apps.accounts.models import User
from django.http import JsonResponse

from apps.products.models import Category, Brand, Product, Review, Wishlist
from apps.analytics.services import get_top_products
from apps.activity.models import UserEvent


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

    # Special offer products: discount 30% or more and available in stock
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
        if product.is_offer_active
    ]

    # Filter by brand
    brand_slug = request.GET.get('brand')
    if brand_slug:
        products = products.filter(brand__slug=brand_slug)

    # Filter by category
    category_slug = request.GET.get('category')
    if category_slug:
        products = products.filter(category__slug=category_slug)

    # Get wishlist product IDs for current user
    wishlist_ids = set()
    if request.user.is_authenticated:
        wishlist_ids = set(
            Wishlist.objects.filter(
                user=request.user
            ).values_list('product_id', flat=True)
        )

    # Search by name, brand name, category name, and description
    q = request.GET.get('q')
    if q:
        products = products.filter(
            Q(name__icontains=q) |
            Q(description__icontains=q) |
            Q(brand__name__icontains=q) |
            Q(category__name__icontains=q)
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

    dist_raw = reviews_qs.values('rating').annotate(count=Count('rating'))
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
    product = get_object_or_404(Product, slug=slug, is_active=True)

    if request.method == 'POST':
        if Review.objects.filter(product=product, customer=request.user).exists():
            messages.warning(request, 'You have already reviewed this product.')
            return redirect('products:product_detail', slug=slug)

        rating = request.POST.get('rating')
        comment = request.POST.get('comment', '').strip()

        if not rating or not comment:
            messages.error(request, 'Please provide both a rating and a comment.')
            return redirect('products:product_detail', slug=slug)

        try:
            rating = int(rating)
        except ValueError:
            messages.error(request, 'Invalid rating value.')
            return redirect('products:product_detail', slug=slug)

        if not (1 <= rating <= 5):
            messages.error(request, 'Rating must be between 1 and 5.')
            return redirect('products:product_detail', slug=slug)

        Review.objects.create(
            product=product,
            customer=request.user,
            rating=rating,
            comment=comment
        )

        UserEvent.objects.create(
            user=request.user,
            product=product,
            event_type='REVIEW'
        )

        messages.success(request, 'Your review has been posted.')

    return redirect('products:product_detail', slug=slug)


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
        name        = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        image       = request.FILES.get('image')

        if not name:
            messages.error(request, 'Category name is required.')
            return redirect('products:category_edit', pk=pk)

        category.name        = name
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
        name        = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        logo        = request.FILES.get('logo')
        order       = request.POST.get('order', '0').strip()

        if not name:
            messages.error(request, 'Brand name is required.')
            return redirect('products:brand_edit', pk=pk)

        brand.name        = name
        brand.description = description
        brand.order       = int(order) if order.isdigit() else 0
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

@login_required
@staff_member_required
def product_list(request):
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
        name           = request.POST.get('name', '').strip()
        description    = request.POST.get('description', '').strip()
        price          = request.POST.get('price', '').strip()
        discount_price = request.POST.get('discount_price', '').strip()
        stock          = request.POST.get('stock', '').strip()
        category_id    = request.POST.get('category')
        brand_id       = request.POST.get('brand')
        is_active      = request.POST.get('is_active') == 'on'
        image          = request.FILES.get('image')

        errors = []
        if not name:
            errors.append('Product name is required.')
        if not category_id:
            errors.append('Category is required.')

        try:
            price = float(price)
        except ValueError:
            errors.append('Price must be a valid number.')
            price = None

        if discount_price:
            try:
                discount_price = float(discount_price)
            except ValueError:
                errors.append('Discount price must be a valid number.')
                discount_price = None
        else:
            discount_price = None

        try:
            stock = int(stock)
        except ValueError:
            errors.append('Stock must be a whole number.')
            stock = None

        if errors:
            for e in errors:
                messages.error(request, e)
            return redirect('products:product_edit', pk=pk)

        product.name           = name
        product.description    = description
        product.price          = price
        product.discount_price = discount_price
        product.stock          = stock
        product.category_id    = category_id
        product.brand_id       = brand_id or None
        product.is_active      = is_active
        if image:
            product.image = image
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
        name        = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        image       = request.FILES.get('image')

        if not name:
            messages.error(request, 'Category name is required.')
            return redirect('products:category_add')

        if Category.objects.filter(name__iexact=name).exists():
            messages.error(request, f"A category named '{name}' already exists.")
            return redirect('products:category_add')

        category = Category.objects.create(name=name, description=description)
        if image:
            category.image = image
            category.save()

        messages.success(request, f"'{category.name}' created.")
        return redirect('products:category_list')

    return render(request, 'products/category_add.html')


@login_required
@staff_member_required
def brand_add(request):
    if request.method == 'POST':
        name        = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        logo        = request.FILES.get('logo')
        order       = request.POST.get('order', '0').strip()

        if not name:
            messages.error(request, 'Brand name is required.')
            return redirect('products:brand_add')

        if Brand.objects.filter(name__iexact=name).exists():
            messages.error(request, f"A brand named '{name}' already exists.")
            return redirect('products:brand_add')

        brand = Brand.objects.create(
            name=name,
            description=description,
            order=int(order) if order.isdigit() else 0,
        )
        if logo:
            brand.logo = logo
            brand.save()

        messages.success(request, f"'{brand.name}' created.")
        return redirect('products:brand_list')

    return render(request, 'products/brand_add.html')


@login_required
@staff_member_required
def product_add(request):
    categories = Category.objects.order_by('name')
    brands     = Brand.objects.order_by('order', 'name')

    if request.method == 'POST':
        name           = request.POST.get('name', '').strip()
        description    = request.POST.get('description', '').strip()
        price          = request.POST.get('price', '').strip()
        discount_price = request.POST.get('discount_price', '').strip()
        stock          = request.POST.get('stock', '').strip()
        category_id    = request.POST.get('category')
        brand_id       = request.POST.get('brand')
        is_active      = request.POST.get('is_active') == 'on'
        image          = request.FILES.get('image')

        errors = []
        if not name:
            errors.append('Product name is required.')
        if not category_id:
            errors.append('Category is required.')

        try:
            price = float(price)
        except ValueError:
            errors.append('Price must be a valid number.')
            price = None

        if discount_price:
            try:
                discount_price = float(discount_price)
            except ValueError:
                errors.append('Discount price must be a valid number.')
                discount_price = None
        else:
            discount_price = None

        try:
            stock = int(stock) if stock else 0
        except ValueError:
            errors.append('Stock must be a whole number.')
            stock = None

        if errors:
            for e in errors:
                messages.error(request, e)
            return render(request, 'products/product_add.html', {
                'categories': categories,
                'brands':     brands,
                'form_data':  request.POST,
            })

        product = Product.objects.create(
            name=name,
            description=description,
            price=price,
            discount_price=discount_price,
            stock=stock,
            category_id=category_id,
            brand_id=brand_id or None,
            is_active=is_active,
        )
        if image:
            product.image = image
            product.save()

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