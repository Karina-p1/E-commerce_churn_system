from django.shortcuts import render, get_object_or_404, redirect
from apps.products.models import Category, Brand, Product, ProductImage, Review
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Avg, Count
from django.db.models import Q


def view_products(request):
    categories = Category.objects.all()
    brands = Brand.objects.all()
    products = Product.objects.filter(
        is_active=True).select_related('category', 'brand')

    # Filter by brand
    brand_slug = request.GET.get('brand')
    if brand_slug:
        products = products.filter(brand__slug=brand_slug)

    # Filter by category
    category_slug = request.GET.get('category')
    if category_slug:
        products = products.filter(category__slug=category_slug)

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
    })

# views.py


def build_stars(rating):
    """Returns list of booleans: True = filled star, False = empty"""
    return [i < round(rating) for i in range(5)]


def product_detail(request, slug):
    product = get_object_or_404(Product, slug=slug, is_active=True)

    reviews_qs = product.reviews.select_related(
        'customer').order_by('-created_at')
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

    # Pre-build star lists so templates don't need float comparisons
    product_stars = build_stars(product.rating)
    review_stars = {r.id: build_stars(r.rating) for r in reviews_qs}

    return render(request, 'products/product_detail.html', {
        'product': product,
        'reviews': reviews_qs,
        'rating_distribution': rating_distribution,
        'product_stars': product_stars,
        'review_stars': review_stars,
    })


# @login_required
def post_review(request, slug):
    product = get_object_or_404(Product, slug=slug, is_active=True)

    if request.method == 'POST':

        # Prevent duplicate reviews
        if Review.objects.filter(product=product, customer=request.user).exists():
            messages.warning(
                request, 'You have already reviewed this product.')
            return redirect('products:product_detail', slug=slug)

        rating = request.POST.get('rating')
        comment = request.POST.get('comment', '').strip()

        # Validate inputs
        if not rating or not comment:
            messages.error(
                request, 'Please provide both a rating and a comment.')
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
        messages.success(request, 'Your review has been posted.')

    return redirect('products:product_detail', slug=slug)
