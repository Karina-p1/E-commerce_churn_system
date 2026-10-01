from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.products.models import Brand, Category, Product, Review


User = get_user_model()


def make_product(category, **overrides):
    payload = {
        "category": category,
        "name": "Test Hoodie",
        "description": "A warm hoodie for cold Kathmandu evenings.",
        "price": Decimal("2500.00"),
        "stock": 10,
    }
    payload.update(overrides)
    return Product.objects.create(**payload)


def valid_product_payload(category_obj, **overrides):
    payload = {
        "name": "Test Hoodie",
        "description": "A warm hoodie for cold Kathmandu evenings.",
        "price": "2500",
        "discount_percentage": "0",
        "stock": "10",
        "category": str(category_obj.pk),
        "brand": "",
        "is_active": "on",
        "offer_start": "",
        "offer_end": "",
    }
    payload.update(overrides)
    return payload


class ProductAddViewTests(TestCase):

    def setUp(self):
        self.staff = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="test-password-123",
        )
        self.category = Category.objects.create(name="Clothing")
        self.client.force_login(self.staff)
        self.url = reverse("products:product_add")

    def test_creates_a_valid_product(self):
        response = self.client.post(
            self.url, valid_product_payload(self.category)
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Product.objects.count(), 1)

    def test_rejects_a_negative_price(self):
        response = self.client.post(
            self.url, valid_product_payload(self.category, price="-5")
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Product.objects.count(), 0)
        self.assertContains(response, "Price cannot be negative")

    def test_rejects_a_zero_price(self):
        response = self.client.post(
            self.url, valid_product_payload(self.category, price="0")
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Product.objects.count(), 0)

    def test_rejects_a_non_numeric_price(self):
        response = self.client.post(
            self.url, valid_product_payload(self.category, price="cheap")
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Product.objects.count(), 0)

    def test_rejects_negative_stock(self):
        response = self.client.post(
            self.url, valid_product_payload(self.category, stock="-3")
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Product.objects.count(), 0)
        self.assertContains(response, "Stock cannot be less than 0")

    def test_rejects_a_missing_category(self):
        response = self.client.post(
            self.url, valid_product_payload(self.category, category="")
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Product.objects.count(), 0)

    def test_rejects_a_category_that_does_not_exist(self):
        response = self.client.post(
            self.url, valid_product_payload(self.category, category="99999")
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Product.objects.count(), 0)
        self.assertContains(response, "category does not exist")

    def test_rejects_a_non_numeric_category_instead_of_crashing(self):
        """`filter(pk='abc')` raises ValueError rather than matching nothing."""
        response = self.client.post(
            self.url, valid_product_payload(self.category, category="abc")
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Product.objects.count(), 0)

    def test_rejects_a_non_numeric_brand_instead_of_crashing(self):
        response = self.client.post(
            self.url, valid_product_payload(self.category, brand="xyz")
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Product.objects.count(), 0)
        self.assertContains(response, "brand does not exist")

    def test_rejects_a_discount_over_one_hundred(self):
        response = self.client.post(
            self.url,
            valid_product_payload(self.category, discount_percentage="150"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Product.objects.count(), 0)

    def test_rejects_a_backwards_offer_window(self):
        response = self.client.post(
            self.url,
            valid_product_payload(
                self.category,
                offer_start="2026-06-01T10:00",
                offer_end="2026-05-01T10:00",
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Product.objects.count(), 0)
        self.assertContains(response, "must be after")

    def test_rejects_a_too_short_description(self):
        response = self.client.post(
            self.url, valid_product_payload(self.category, description="hi")
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Product.objects.count(), 0)

    def test_rejects_an_oversized_image(self):
        oversized = SimpleUploadedFile(
            "huge.png",
            b"0" * (6 * 1024 * 1024),
            content_type="image/png",
        )

        response = self.client.post(
            self.url,
            {**valid_product_payload(self.category), "image": oversized},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Product.objects.count(), 0)

    def test_error_page_keeps_the_submitted_values(self):
        response = self.client.post(
            self.url,
            valid_product_payload(self.category, name="Cool Hoodie", price="-1"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["form_data"]["name"], "Cool Hoodie")


class ProductEditViewTests(TestCase):

    def setUp(self):
        self.staff = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="test-password-123",
        )
        self.category = Category.objects.create(name="Clothing")
        self.product = make_product(self.category)
        self.client.force_login(self.staff)
        self.url = reverse("products:product_edit", args=[self.product.pk])

    def test_updates_a_valid_product(self):
        response = self.client.post(
            self.url,
            valid_product_payload(self.category, price="3000"),
        )

        self.assertEqual(response.status_code, 302)
        self.product.refresh_from_db()
        self.assertEqual(self.product.price, Decimal("3000.00"))

    def test_error_page_still_renders_with_an_active_offer(self):
        """
        The edit template prints product.effective_price when an offer is
        live. That is Decimal arithmetic, so the preview has to hold real
        numbers, not the raw POST strings.
        """
        now = timezone.now()
        started = now - timedelta(days=1)
        ends = now + timedelta(days=1)

        self.product.discount_percentage = 20
        self.product.offer_start = started
        self.product.offer_end = ends
        self.product.save()

        response = self.client.post(
            self.url,
            valid_product_payload(
                self.category,
                price="-5",
                discount_percentage="20",
                offer_start=started.strftime("%Y-%m-%dT%H:%M"),
                offer_end=ends.strftime("%Y-%m-%dT%H:%M"),
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["product"].is_offer_active)
        self.assertContains(response, "Offer currently active")


class BrandAdminTests(TestCase):

    def setUp(self):
        self.staff = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="test-password-123",
        )
        self.client.force_login(self.staff)

    def test_creates_a_valid_brand(self):
        response = self.client.post(
            reverse("products:brand_add"),
            {"name": "North Peak", "description": "Outdoor gear", "order": "1"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Brand.objects.count(), 1)

    def test_rejects_a_duplicate_brand_name(self):
        Brand.objects.create(name="North Peak")

        response = self.client.post(
            reverse("products:brand_add"),
            {"name": "north peak", "description": "", "order": "0"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Brand.objects.count(), 1)
        self.assertContains(response, "already exists")

    def test_rejects_a_duplicate_brand_name_on_edit(self):
        Brand.objects.create(name="North Peak")
        other = Brand.objects.create(name="South Trail")

        response = self.client.post(
            reverse("products:brand_edit", args=[other.pk]),
            {"name": "North Peak", "description": "", "order": "0"},
        )

        self.assertEqual(response.status_code, 200)
        other.refresh_from_db()
        self.assertEqual(other.name, "South Trail")

    def test_brand_edit_allows_keeping_its_own_name(self):
        brand = Brand.objects.create(name="North Peak")

        response = self.client.post(
            reverse("products:brand_edit", args=[brand.pk]),
            {"name": "North Peak", "description": "Gear", "order": "2"},
        )

        self.assertEqual(response.status_code, 302)
        brand.refresh_from_db()
        self.assertEqual(brand.description, "Gear")

    def test_brand_edit_keeps_input_after_an_error(self):
        brand = Brand.objects.create(name="North Peak")

        response = self.client.post(
            reverse("products:brand_edit", args=[brand.pk]),
            {"name": "N", "description": "Typed this", "order": "0"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["brand"].description, "Typed this")

    def test_rejects_a_negative_display_order(self):
        response = self.client.post(
            reverse("products:brand_add"),
            {"name": "North Peak", "description": "", "order": "-2"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Brand.objects.count(), 0)


class CategoryAdminTests(TestCase):

    def setUp(self):
        self.staff = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="test-password-123",
        )
        self.client.force_login(self.staff)

    def test_creates_a_valid_category(self):
        response = self.client.post(
            reverse("products:category_add"),
            {"name": "Footwear", "description": "Shoes and sandals"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Category.objects.count(), 1)

    def test_rejects_a_duplicate_category_name(self):
        Category.objects.create(name="Footwear")

        response = self.client.post(
            reverse("products:category_add"),
            {"name": "footwear", "description": ""},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Category.objects.count(), 1)

    def test_rejects_a_duplicate_category_name_on_edit(self):
        Category.objects.create(name="Footwear")
        other = Category.objects.create(name="Accessories")

        response = self.client.post(
            reverse("products:category_edit", args=[other.pk]),
            {"name": "Footwear", "description": ""},
        )

        self.assertEqual(response.status_code, 200)
        other.refresh_from_db()
        self.assertEqual(other.name, "Accessories")


class PostReviewViewTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username="customer",
            email="customer@example.com",
            password="test-password-123",
        )
        self.category = Category.objects.create(name="Clothing")
        self.product = make_product(self.category, slug="test-hoodie")
        self.client.force_login(self.user)
        self.url = reverse(
            "products:post_review", kwargs={"slug": self.product.slug}
        )

    def test_accepts_a_valid_review(self):
        response = self.client.post(
            self.url,
            {
                "action": "review",
                "rating": "4",
                "comment": "Good quality hoodie, fits well.",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Review.objects.count(), 1)

    def test_rejects_a_too_short_comment(self):
        response = self.client.post(
            self.url,
            {"action": "review", "rating": "4", "comment": "nice"},
        )

        self.assertEqual(Review.objects.count(), 0)

    def test_rejects_a_comment_over_two_thousand_characters(self):
        response = self.client.post(
            self.url,
            {"action": "review", "rating": "4", "comment": "x" * 2001},
        )

        self.assertEqual(Review.objects.count(), 0)

    def test_rejects_an_out_of_range_rating(self):
        response = self.client.post(
            self.url,
            {
                "action": "review",
                "rating": "9",
                "comment": "This rating is not allowed at all.",
            },
        )

        self.assertEqual(Review.objects.count(), 0)

    def test_rejects_a_missing_rating(self):
        response = self.client.post(
            self.url,
            {
                "action": "review",
                "rating": "",
                "comment": "A comment without a rating is not allowed.",
            },
        )

        self.assertEqual(Review.objects.count(), 0)


class ProductTemplateRenderTests(TestCase):
    """
    The admin templates touched by the validation work must render, both
    empty and with an error to display.
    """

    def setUp(self):
        self.staff = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="test-password-123",
        )
        self.category = Category.objects.create(name="Clothing")
        self.product = make_product(self.category)
        self.client.force_login(self.staff)

    def test_product_add_renders(self):
        response = self.client.get(reverse("products:product_add"))

        self.assertEqual(response.status_code, 200)

    def test_product_add_renders_with_errors(self):
        response = self.client.post(
            reverse("products:product_add"),
            valid_product_payload(self.category, price="-1"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Price cannot be negative")

    def test_product_edit_renders(self):
        response = self.client.get(
            reverse("products:product_edit", args=[self.product.pk])
        )

        self.assertEqual(response.status_code, 200)

    def test_product_edit_renders_with_errors(self):
        response = self.client.post(
            reverse("products:product_edit", args=[self.product.pk]),
            valid_product_payload(self.category, stock="abc"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "whole number")

    def test_brand_add_renders(self):
        response = self.client.get(reverse("products:brand_add"))

        self.assertEqual(response.status_code, 200)

    def test_brand_add_renders_with_errors(self):
        response = self.client.post(
            reverse("products:brand_add"),
            {"name": "N", "description": "", "order": "0"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "at least 2 characters")

    def test_brand_edit_renders(self):
        brand = Brand.objects.create(name="North Peak")

        response = self.client.get(
            reverse("products:brand_edit", args=[brand.pk])
        )

        self.assertEqual(response.status_code, 200)

    def test_brand_edit_renders_with_errors(self):
        brand = Brand.objects.create(name="North Peak")

        response = self.client.post(
            reverse("products:brand_edit", args=[brand.pk]),
            {"name": "", "description": "", "order": "0"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "required")

    def test_category_add_renders(self):
        response = self.client.get(reverse("products:category_add"))

        self.assertEqual(response.status_code, 200)

    def test_category_add_renders_with_errors(self):
        Category.objects.create(name="Footwear")

        response = self.client.post(
            reverse("products:category_add"),
            {"name": "footwear", "description": ""},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already exists")

    def test_category_edit_renders_with_errors(self):
        Category.objects.create(name="Footwear")
        other = Category.objects.create(name="Accessories")

        response = self.client.post(
            reverse("products:category_edit", args=[other.pk]),
            {"name": "Footwear", "description": ""},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already exists")

    def test_product_detail_renders_with_review_form(self):
        self.client.force_login(
            User.objects.create_user(
                username="customer",
                email="customer@example.com",
                password="test-password-123",
            )
        )

        response = self.client.get(
            reverse("products:product_detail", args=[self.product.slug])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="comment"')
        self.assertContains(response, 'minlength="10"')
        self.assertContains(response, "ratingError")
