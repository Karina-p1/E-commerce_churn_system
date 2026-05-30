from datetime import timedelta
from django.utils import timezone

from .models import UserEvent
from apps.products.models import Product


class UserActivityMiddleware:

    def __init__(self, get_response):
        self.get_response = get_response


    def __call__(self, request):

        response = self.get_response(request)

        if request.user.is_authenticated:

            path = request.path

            if '/products/' in path:

                try:
                    product_id = path.strip('/').split("/")[-1]

                    product = Product.objects.get(id=product_id)

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

                except:
                    pass

        return response