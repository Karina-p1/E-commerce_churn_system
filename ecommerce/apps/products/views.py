from datetime import timedelta

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from django.db.models import Count
from django.utils import timezone
from flask import Response

from apps.products.models import Category, Brand, Product, Review, Wishlist
from apps.analytics.services import get_top_products
from apps.activity.models import UserEvent


def view_products(request):
    categories = Category.objects.all()
    top_products = get_top_products(limit=10)
    brands = Brand.objects.all()

    products = Product.objects.filter(
        is_active=True
    ).select_related(
        'category',
        'brand'
    )

    # Special offer products: discount 30% or more and available in stock
    # This is calculated before filters/search so the slider always shows homepage offers.
    all_active_products = Product.objects.filter(
        is_active=True,
        stock__gt=0
    ).select_related(
        'category',
        'brand'
    )

    special_offers = [
        product for product in all_active_products
        if product.discount_percent and product.discount_percent >= 30
    ]

    # Filter by brand
    brand_slug = request.GET.get('brand')
    if brand_slug:
        products = products.filter(
            brand__slug=brand_slug
        )

    # Filter by category
    category_slug = request.GET.get('category')
    if category_slug:
        products = products.filter(
            category__slug=category_slug
        )

    # Get wishlist product IDs for current user
    wishlist_ids = set()

    if request.user.is_authenticated:
        wishlist_ids = set(
            Wishlist.objects.filter(
                user=request.user
            ).values_list(
                'product_id',
                flat=True
            )
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

    wishlist_item = Wishlist.objects.filter(
        user=request.user,
        product=product
    ).first()

    if wishlist_item:
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
        Wishlist.objects.create(
            user=request.user,
            product=product
        )

        UserEvent.objects.create(
            user=request.user,
            product=product,
            event_type='WISHLIST'
        )

        messages.success(
            request,
            f"'{product.name}' added to wishlist ❤️"
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

def top_products(request):
    today = timezone.now()
    month_start = today.replace(
        day=1, hour=0, minute=0, second=0, microsecond=0)

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
            'name':          p.name,
            'category':      p.category.name if p.category else 'Uncategorized',
            'brand':         p.brand.name if p.brand else '',
            'rating':        float(p.rating) if p.rating else 0,
            'order_count':   p.order_count,
            'wishlist_count': p.wishlist_count,
            'view_count':    p.view_count,
        }
        for p in top
    ]

    return Response(data)