from .models import Category, Brand


def navbar_data(request):
    return {
        'all_categories': Category.objects.all(),
        'all_brands': Brand.objects.all(),
    }
