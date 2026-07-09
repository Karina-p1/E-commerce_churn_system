from django.db import models
from django.utils.text import slugify

from django.conf import settings
from decimal import Decimal
from django.utils import timezone

class Brand(models.Model):
    name        = models.CharField(max_length=100)
    slug        = models.SlugField(unique=True, blank=True)
    logo        = models.ImageField(upload_to='brands/', blank=True, null=True)
    description = models.TextField(blank=True)
    order       = models.PositiveIntegerField(
        default=0,
        help_text="Lower number appears first in the brand strip. Set by admin."
    )
    created_at  = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Category(models.Model):
    name        = models.CharField(max_length=100)
    slug        = models.SlugField(unique=True, blank=True)
    description = models.TextField(blank=True)
    image       = models.ImageField(upload_to='categories/', blank=True, null=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    class Meta:
        verbose_name_plural = "Categories"

    def __str__(self):
        return self.name


class Product(models.Model):
    category       = models.ForeignKey(
        Category, on_delete=models.CASCADE, related_name='products')
    brand          = models.ForeignKey(
        Brand, on_delete=models.SET_NULL, null=True, blank=True, related_name='products')
    name           = models.CharField(max_length=255)
    slug           = models.SlugField(unique=True, blank=True)
    description    = models.TextField()
    price          = models.DecimalField(max_digits=10, decimal_places=2)
    discount_percentage = models.PositiveIntegerField(default=0)
    stock          = models.IntegerField(default=0)
    image          = models.ImageField(upload_to='products/main/', blank=True, null=True)
    is_active      = models.BooleanField(default=True)
    created_at     = models.DateTimeField(auto_now_add=True)
    updated_at     = models.DateTimeField(auto_now=True)

    offer_start = models.DateTimeField(
        null=True,
        blank=True
    )

    offer_end = models.DateTimeField(
        null=True,
        blank=True
    )

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    @property
    def rating(self):
        reviews = self.reviews.all()
        if reviews.exists():
            return round(sum(r.rating for r in reviews) / reviews.count(), 1)
        return 0.0

    @property
    def review_count(self):
        return self.reviews.count()
    
    @property
    def is_offer_active(self):
        now = timezone.now()

        if self.discount_percentage <= 0:
            return False

        if self.offer_start and now < self.offer_start:
            return False

        if self.offer_end and now > self.offer_end:
            return False

        return True

    @property
    def discount_percent(self):
        if self.is_offer_active:
            return self.discount_percentage
        return 0

    @property
    def effective_price(self):
        if self.is_offer_active:
            discount = Decimal(self.discount_percentage) / Decimal("100")
            return self.price * (Decimal("1") - discount)

        return self.price
    
    @property
    def is_special_offer(self):
        if self.discount_percent < 30:
            return False

        now = timezone.now()

        if self.offer_start and now < self.offer_start:
            return False

        if self.offer_end and now > self.offer_end:
            return False

        return True

    def __str__(self):
        return self.name


class ProductImage(models.Model):
    product    = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')
    image      = models.ImageField(upload_to='products/gallery/', blank=True, null=True)
    is_primary = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.product.name} - image"


class Review(models.Model):
    product    = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='reviews')
    customer   = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    rating     = models.IntegerField()
    comment    = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)


class Wishlist(models.Model):
    user    = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="wishlist"
    )
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="wishlisted_by"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'product')

    def __str__(self):
        return f"{self.user.username} - {self.product.name}"