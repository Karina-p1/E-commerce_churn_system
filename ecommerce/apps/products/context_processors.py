from .models import Category, Brand


def navbar_data(request):
    return {
        'all_categories': Category.objects.all().order_by('name'),
        'all_brands': Brand.objects.all().order_by('order', 'name'),
    }