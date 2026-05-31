from datetime import timedelta

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from django.db.models import Count
from django.utils import timezone

from apps.products.models import Category, Brand, Product, Review, Wishlist

from apps.activity.models import UserEvent


def view_products(request):
    categories = Category.objects.all()
    brands = Brand.objects.all()

    products = Product.objects.filter(
        is_active=True
    ).select_related(
        'category',
        'brand'
    )

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
            Wishlist.objects.filter(user=request.user)
            .values_list('product_id', flat=True)
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
        "all_brands": brands,
        "all_categories": categories,
        "active_brand": brand_slug,
        "active_category": category_slug,
        "wishlist_ids": wishlist_ids,
    })


def build_stars(rating):
    """
    Returns list of booleans:
    True = filled star
    False = empty star
    """
    return [i < round(rating) for i in range(5)]


def product_detail(request, slug):
    product = get_object_or_404(
        Product,
        slug=slug,
        is_active=True
    )

    # Activity tracking: product view
    # Logs VIEW only once per product per user within 5 minutes.
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

    reviews_qs = product.reviews.select_related(
        'customer'
    ).order_by(
        '-created_at'
    )

    total = reviews_qs.count()

    dist_raw = reviews_qs.values(
        'rating'
    ).annotate(
        count=Count('rating')
    )

    dist_map = {
        d['rating']: d['count']
        for d in dist_raw
    }

    rating_distribution = [
        {
            'label': star,
            'count': dist_map.get(star, 0),
            'pct': round(dist_map.get(star, 0) / total * 100) if total else 0,
        }
        for star in range(5, 0, -1)
    ]

    product_stars = build_stars(product.rating)

    review_stars = {
        review.id: build_stars(review.rating)
        for review in reviews_qs
    }

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
        comment = request.POST.get('comment', '').strip()

        if not rating or not comment:
            messages.error(
                request,
                'Please provide both a rating and a comment.'
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
    product = get_object_or_404(
        Product,
        id=product_id,
        is_active=True
    )

    obj, created = Wishlist.objects.get_or_create(
        user=request.user,
        product=product
    )

    if created:
        UserEvent.objects.create(
            user=request.user,
            product=product,
            event_type='WISHLIST'
        )

        messages.success(
            request,
            f"'{product.name}' added to wishlist ❤️"
        )
    else:
        messages.info(
            request,
            f"'{product.name}' is already in your wishlist."
        )

    return redirect(
        request.META.get(
            'HTTP_REFERER',
            'products:view_products'
        )
    )

@login_required
def wishlist_view(request):
    items = Wishlist.objects.filter(
        user=request.user).select_related('product')
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

        UserEvent.objects.create(
            user=request.user,
            product=product,
            event_type='REMOVE_WISHLIST'
        )

        messages.info(
            request,
            f"'{product.name}' removed from wishlist."
        )
    else:
        messages.warning(
            request,
            "This product was not in your wishlist."
        )

    return redirect('products:wishlist')
