from django.shortcuts import render
from apps.products.models import Category, Brand, Product, ProductImage


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
