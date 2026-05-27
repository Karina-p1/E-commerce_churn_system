from django.shortcuts import render, get_object_or_404, redirect
from apps.products.models import Category, Brand, Product, ProductImage, Review
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Avg, Count


def view_products(request):
    categories = Category.objects.all()
    brands = Brand.objects.all()
    products = Product.objects.filter(
        is_active=True).select_related('category', 'brand')

    return render(request, "products/dashboard.html", {
        "categories": categories,
        "brands": brands,
        "products": products,
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


@login_required
def post_review(request, slug):
    product = get_object_or_404(Product, slug=slug, is_active=True)

    # Prevent duplicate reviews
    if Review.objects.filter(product=product, customer=request.user).exists():
        messages.warning(request, 'You have already reviewed this product.')
        return redirect('products:product_detail', slug=slug)

    if request.method == 'POST':
        rating = request.POST.get('rating')
        comment = request.POST.get('comment', '').strip()

        # Validate inputs
        if not rating or not comment:
            messages.error(
                request, 'Please provide both a rating and a comment.')
            return redirect('products:product_detail', slug=slug)

        if not (1 <= int(rating) <= 5):
            messages.error(request, 'Rating must be between 1 and 5.')
            return redirect('products:product_detail', slug=slug)

        Review.objects.create(
            product=product,
            customer=request.user,
            rating=int(rating),
            comment=comment
        )
        messages.success(request, 'Your review has been posted.')

    return redirect('products:product_detail', slug=slug)
