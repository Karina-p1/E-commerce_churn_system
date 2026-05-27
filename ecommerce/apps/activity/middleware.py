from .models import UserEvent
from apps.products.models import Product


class UserActivityMiddleware:

    def __init__(self,get_response):

        self.get_response=get_response


    def __call__(self,request):

        response=self.get_response(request)

        if request.user.is_authenticated:

            path=request.path

            if '/products/' in path:

                try:

                    product_id=path.split("/")[-2]

                    product=Product.objects.get(
                        id=product_id
                    )

                    UserEvent.objects.create(
                        user=request.user,
                        product=product,
                        event_type='VIEW'
                    )

                except:

                    pass

        return response