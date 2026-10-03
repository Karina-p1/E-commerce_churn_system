from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.orders.forms import RefundRequestForm
from apps.orders.models import (
    Cart,
    CartItem,
    Coupon,
    Order,
    OrderItem,
    RefundRequest,
)
from apps.addresses.models import Address
from apps.loyalty.models import LoyaltyTier
from apps.notifications.models import Notification
from apps.products.models import Category, Product


User = get_user_model()


def make_order(user, **overrides):
    payload = {"user": user, "total_price": Decimal("2000.00")}
    payload.update(overrides)
    return Order.objects.create(**payload)


def add_item(order, name, quantity=1, product=None):
    return OrderItem.objects.create(
        order=order,
        product=product,
        product_name=name,
        price=Decimal("1000.00"),
        quantity=quantity,
    )


def valid_refund_payload(**overrides):
    payload = {
        "reason": "DAMAGED",
        "other_reason": "",
        "bank_name": "NIC Asia",
        "account_holder": "Saugat Karki",
        "account_number": "1234567890123",
        "branch": "Koteshwor",
        "phone": "9812345678",
    }
    payload.update(overrides)
    return payload


def valid_coupon_payload(**overrides):
    payload = {
        "code": "SAVE10",
        "coupon_type": "STANDARD",
        "discount_type": "PERCENTAGE",
        "discount_value": "10",
        "min_order_amount": "500",
        "max_uses": "100",
        "get_discount_percent": "100",
        "is_active": "on",
        "valid_from": "",
        "valid_until": "",
    }
    payload.update(overrides)
    return payload


class RefundRequestFormTests(TestCase):

    def test_accepts_a_complete_request(self):
        form = RefundRequestForm(data=valid_refund_payload())

        self.assertTrue(form.is_valid(), form.errors)

    def test_rejects_a_missing_phone(self):
        form = RefundRequestForm(data=valid_refund_payload(phone=""))

        self.assertFalse(form.is_valid())
        self.assertIn("phone", form.errors)

    def test_rejects_a_non_mobile_phone(self):
        form = RefundRequestForm(data=valid_refund_payload(phone="1234567890"))

        self.assertFalse(form.is_valid())
        self.assertIn("phone", form.errors)

    def test_normalizes_the_phone_number(self):
        form = RefundRequestForm(
            data=valid_refund_payload(phone="+977-9812345678")
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["phone"], "9812345678")

    def test_rejects_a_non_numeric_account_number(self):
        form = RefundRequestForm(
            data=valid_refund_payload(account_number="12-34-ABCD")
        )

        self.assertFalse(form.is_valid())
        self.assertIn("account_number", form.errors)

    def test_strips_spaces_from_the_account_number(self):
        form = RefundRequestForm(
            data=valid_refund_payload(account_number="1234 5678 9012")
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["account_number"], "123456789012")

    def test_rejects_a_too_short_account_number(self):
        form = RefundRequestForm(data=valid_refund_payload(account_number="12"))

        self.assertFalse(form.is_valid())
        self.assertIn("account_number", form.errors)

    def test_rejects_an_unknown_reason(self):
        form = RefundRequestForm(data=valid_refund_payload(reason="BECAUSE"))

        self.assertFalse(form.is_valid())
        self.assertIn("reason", form.errors)

    def test_other_reason_is_required_when_reason_is_other(self):
        form = RefundRequestForm(
            data=valid_refund_payload(reason="OTHER", other_reason="")
        )

        self.assertFalse(form.is_valid())
        self.assertIn("other_reason", form.errors)

    def test_other_reason_is_not_required_for_a_named_reason(self):
        form = RefundRequestForm(data=valid_refund_payload(reason="DELAYED"))

        self.assertTrue(form.is_valid(), form.errors)

    def test_rejects_an_account_holder_with_digits(self):
        form = RefundRequestForm(
            data=valid_refund_payload(account_holder="Saugat 98123")
        )

        self.assertFalse(form.is_valid())
        self.assertIn("account_holder", form.errors)


class RequestRefundViewTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username="customer",
            email="customer@example.com",
            password="test-password-123",
        )
        self.order = make_order(self.user, payment_status="PAID")
        self.client.force_login(self.user)

    def test_valid_request_is_saved(self):
        response = self.client.post(
            reverse("request_refund", args=[self.order.pk]),
            valid_refund_payload(),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(RefundRequest.objects.count(), 1)
        self.assertEqual(
            RefundRequest.objects.first().phone, "9812345678"
        )

    def test_invalid_request_re_renders_with_errors(self):
        response = self.client.post(
            reverse("request_refund", args=[self.order.pk]),
            valid_refund_payload(account_number="nope"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(RefundRequest.objects.count(), 0)
        self.assertTrue(response.context["form"].errors)


class CancelOrderViewTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username="customer",
            email="customer@example.com",
            password="test-password-123",
        )
        self.order = make_order(self.user, status="pending")
        self.client.force_login(self.user)

    def test_accepts_a_valid_reason(self):
        response = self.client.post(
            reverse("cancel_order", args=[self.order.pk]),
            {
                "reason": "changed",
                "note": "Ordered this by accident.",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "cancelled")
        self.assertEqual(self.order.cancel_reason, "changed")

    def test_rejects_a_reason_outside_the_model_choices(self):
        response = self.client.post(
            reverse("cancel_order", args=[self.order.pk]),
            {"reason": "BECAUSE_I_SAID_SO", "note": "Changed my mind."},
        )

        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.assertNotEqual(self.order.status, "cancelled")

    def test_rejects_a_missing_reason(self):
        response = self.client.post(
            reverse("cancel_order", args=[self.order.pk]),
            {"reason": "", "note": "Changed my mind."},
        )

        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.assertNotEqual(self.order.status, "cancelled")

    def test_other_reason_requires_a_note(self):
        response = self.client.post(
            reverse("cancel_order", args=[self.order.pk]),
            {"reason": "OTHER", "note": ""},
        )

        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.assertNotEqual(self.order.status, "cancelled")

    def test_error_page_keeps_the_submitted_values(self):
        response = self.client.post(
            reverse("cancel_order", args=[self.order.pk]),
            {"reason": "OTHER", "note": "no"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["reason"], "OTHER")
        self.assertEqual(response.context["note"], "no")


class OrderStatusUpdateTests(TestCase):

    def setUp(self):
        self.staff = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="test-password-123",
        )
        self.order = make_order(self.staff, status="pending")
        self.client.force_login(self.staff)
        self.url = reverse("order_update_status", args=[self.order.pk])

    def test_accepts_a_valid_status(self):
        response = self.client.post(
            self.url,
            {"status": "processing", "note": "Handed to courier"},
        )

        self.assertEqual(response.status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "processing")

    def test_rejects_a_status_outside_the_model_choices(self):
        response = self.client.post(
            self.url,
            {"status": "TELEPORTED", "note": ""},
        )

        self.assertEqual(response.status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "pending")

    def test_rejects_an_over_long_note(self):
        response = self.client.post(
            self.url,
            {"status": "PACKED", "note": "x" * 1001},
        )

        self.assertEqual(response.status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "pending")


class ProcessRefundTests(TestCase):

    def setUp(self):
        self.staff = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="test-password-123",
        )
        self.order = make_order(self.staff, status="delivered", payment_status="PAID")
        self.url = reverse("process_refund", args=[self.order.pk])
        self.client.force_login(self.staff)

    def test_rejects_a_missing_reference_id(self):
        response = self.client.post(
            self.url,
            {"reference_id": "", "notes": "Refunded via eSewa."},
        )

        self.assertEqual(response.status_code, 302)
        self.order.refresh_from_db()
        self.assertNotEqual(self.order.refund_status, "COMPLETED")

    def test_rejects_a_too_short_reference_id(self):
        response = self.client.post(
            self.url,
            {"reference_id": "ab", "notes": "Refunded via eSewa."},
        )

        self.assertEqual(response.status_code, 302)
        self.order.refresh_from_db()
        self.assertNotEqual(self.order.refund_status, "COMPLETED")

    def test_accepts_a_valid_refund(self):
        response = self.client.post(
            self.url,
            {
                "reference_id": "EPAY-998877",
                "notes": "Refunded via eSewa.",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.refund_status, "COMPLETED")


class CouponAdminTests(TestCase):

    def setUp(self):
        self.staff = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="test-password-123",
        )
        self.client.force_login(self.staff)
        self.add_url = reverse("coupon_add")

    def test_creates_a_valid_coupon(self):
        response = self.client.post(self.add_url, valid_coupon_payload())

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Coupon.objects.count(), 1)
        self.assertEqual(Coupon.objects.first().code, "SAVE10")

    def test_rejects_a_percentage_over_one_hundred(self):
        response = self.client.post(
            self.add_url,
            valid_coupon_payload(discount_value="150"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Coupon.objects.count(), 0)
        self.assertContains(response, "cannot be greater than 100")

    def test_rejects_a_non_numeric_discount(self):
        response = self.client.post(
            self.add_url,
            valid_coupon_payload(discount_value="free"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Coupon.objects.count(), 0)

    def test_rejects_a_code_with_illegal_characters(self):
        response = self.client.post(
            self.add_url,
            valid_coupon_payload(code="SAVE 10%"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Coupon.objects.count(), 0)

    def test_rejects_a_duplicate_code(self):
        Coupon.objects.create(code="SAVE10", discount_value=Decimal("10"))

        response = self.client.post(self.add_url, valid_coupon_payload())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Coupon.objects.count(), 1)
        self.assertContains(response, "already exists")

    def test_rejects_an_unknown_coupon_type(self):
        response = self.client.post(
            self.add_url,
            valid_coupon_payload(coupon_type="MYSTERY"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Coupon.objects.count(), 0)

    def test_min_quantity_coupon_needs_a_minimum_quantity(self):
        response = self.client.post(
            self.add_url,
            valid_coupon_payload(coupon_type="MIN_QUANTITY", min_quantity=""),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Coupon.objects.count(), 0)

    def test_buy_x_get_y_needs_both_quantities(self):
        response = self.client.post(
            self.add_url,
            valid_coupon_payload(
                coupon_type="BUY_X_GET_Y",
                buy_quantity="2",
                get_quantity="",
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Coupon.objects.count(), 0)

    def test_rejects_a_backwards_validity_window(self):
        response = self.client.post(
            self.add_url,
            valid_coupon_payload(
                valid_from="2026-06-01T00:00",
                valid_until="2026-05-01T00:00",
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Coupon.objects.count(), 0)
        self.assertContains(response, "must be after")

    def test_rejects_an_unparseable_date(self):
        response = self.client.post(
            self.add_url,
            valid_coupon_payload(valid_from="not-a-date"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Coupon.objects.count(), 0)

    def test_edit_allows_keeping_its_own_code(self):
        coupon = Coupon.objects.create(
            code="SAVE10", discount_value=Decimal("10")
        )

        response = self.client.post(
            reverse("coupon_edit", args=[coupon.pk]),
            valid_coupon_payload(discount_value="20"),
        )

        self.assertEqual(response.status_code, 302)
        coupon.refresh_from_db()
        self.assertEqual(coupon.code, "SAVE10")
        self.assertEqual(coupon.discount_value, Decimal("20.00"))

    def test_edit_keeps_submitted_values_on_error(self):
        coupon = Coupon.objects.create(
            code="SAVE10", discount_value=Decimal("10")
        )

        response = self.client.post(
            reverse("coupon_edit", args=[coupon.pk]),
            valid_coupon_payload(discount_value="500"),
        )

        self.assertEqual(response.status_code, 200)
        coupon.refresh_from_db()
        self.assertEqual(coupon.discount_value, Decimal("10"))
        # The admin's input is still on screen rather than reverted.
        self.assertEqual(response.context["coupon"].code, "SAVE10")


class OrderTemplateRenderTests(TestCase):
    """
    The templates touched by the validation work must render, including
    the error branches that only run after a rejected POST.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="customer",
            email="customer@example.com",
            password="test-password-123",
        )
        self.staff = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="test-password-123",
        )

    def test_cancel_order_page_renders(self):
        order = make_order(self.user, status="pending")
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("cancel_order", args=[order.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="reason"')

    def test_refund_page_renders_with_errors(self):
        order = make_order(self.user, payment_status="PAID")
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("request_refund", args=[order.pk]),
            valid_refund_payload(account_number="nope"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "invalid-feedback")

    def test_checkout_renders_with_a_cart_and_an_address(self):
        """Checkout is a hand-built form, so it has to render for a
        customer who is actually able to reach it."""
        LoyaltyTier.objects.create(
            name="Bronze",
            minimum_points=0,
            points_multiplier=Decimal("1"),
            discount_percentage=Decimal("0"),
        )

        category = Category.objects.create(name="Clothing")
        product = Product.objects.create(
            category=category,
            name="Test Hoodie",
            description="A warm hoodie for cold Kathmandu evenings.",
            price=Decimal("2500.00"),
            stock=10,
        )

        cart = Cart.objects.create(user=self.user)
        CartItem.objects.create(cart=cart, product=product, quantity=1)

        Address.objects.create(
            user=self.user,
            label="Home",
            full_name="Saugat Karki",
            phone="9812345678",
            province="Bagmati",
            district="Kathmandu",
            city="Kathmandu",
            ward="4",
            street="Baneshwor 5",
        )

        self.client.force_login(self.user)

        response = self.client.get(reverse("checkout"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="payment_method"')

    def test_checkout_rejects_an_unknown_payment_method(self):
        LoyaltyTier.objects.create(
            name="Bronze",
            minimum_points=0,
            points_multiplier=Decimal("1"),
            discount_percentage=Decimal("0"),
        )

        category = Category.objects.create(name="Clothing")
        product = Product.objects.create(
            category=category,
            name="Test Hoodie",
            description="A warm hoodie for cold Kathmandu evenings.",
            price=Decimal("2500.00"),
            stock=10,
        )

        cart = Cart.objects.create(user=self.user)
        CartItem.objects.create(cart=cart, product=product, quantity=1)

        address = Address.objects.create(
            user=self.user,
            label="Home",
            full_name="Saugat Karki",
            phone="9812345678",
            province="Bagmati",
            district="Kathmandu",
            city="Kathmandu",
            ward="4",
            street="Baneshwor 5",
        )

        self.client.force_login(self.user)

        response = self.client.post(
            reverse("checkout"),
            {"address": address.pk, "payment_method": "BOGUS"},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Order.objects.count(), 0)
        self.assertContains(response, "Invalid payment method")

    def test_coupon_add_page_renders(self):
        self.client.force_login(self.staff)

        response = self.client.get(reverse("coupon_add"))

        self.assertEqual(response.status_code, 200)

    def test_coupon_add_renders_with_errors(self):
        self.client.force_login(self.staff)

        response = self.client.post(
            reverse("coupon_add"),
            valid_coupon_payload(discount_value="500"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "cannot be greater than 100")

    def test_coupon_edit_renders_with_errors(self):
        coupon = Coupon.objects.create(
            code="SAVE10", discount_value=Decimal("10")
        )
        Coupon.objects.create(code="TAKEN", discount_value=Decimal("5"))
        self.client.force_login(self.staff)

        response = self.client.post(
            reverse("coupon_edit", args=[coupon.pk]),
            valid_coupon_payload(code="TAKEN"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already exists")

    def test_admin_order_list_renders(self):
        make_order(self.staff, status="pending")
        self.client.force_login(self.staff)

        response = self.client.get(reverse("order_list_admin"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "maxlength=\"1000\"")

    def test_admin_order_detail_renders(self):
        order = make_order(self.staff, status="pending")
        self.client.force_login(self.staff)

        response = self.client.get(
            reverse("order_detail_admin", args=[order.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="note"')


class OrderItemsSummaryTests(TestCase):
    """
    Order.items_summary is the single source of the customer-facing order
    label: it must show a product name, add "+n more" for extra line items,
    and never leak an order number when products are known.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="customer",
            email="customer@example.com",
            password="test-password-123",
        )

    def test_single_item_returns_the_product_name(self):
        order = make_order(self.user)
        add_item(order, "Wireless Earbuds", quantity=2)

        self.assertEqual(order.items_summary, "Wireless Earbuds")

    def test_quantity_does_not_count_as_extra_items(self):
        order = make_order(self.user)
        add_item(order, "Wireless Earbuds", quantity=7)

        self.assertEqual(order.items_summary, "Wireless Earbuds")

    def test_multiple_items_append_a_plus_count(self):
        order = make_order(self.user)
        add_item(order, "Wireless Earbuds")
        add_item(order, "Phone Case")
        add_item(order, "USB-C Cable")

        self.assertEqual(
            order.items_summary, "Wireless Earbuds + 2 more"
        )

    def test_two_items_append_plus_one_more(self):
        order = make_order(self.user)
        add_item(order, "Wireless Earbuds")
        add_item(order, "Phone Case")

        self.assertEqual(
            order.items_summary, "Wireless Earbuds + 1 more"
        )

    def test_falls_back_to_the_order_number_when_there_are_no_items(self):
        order = make_order(self.user)

        self.assertEqual(order.items_summary, f"Order #{order.id}")

    def test_blank_product_name_still_produces_a_label(self):
        order = make_order(self.user)
        add_item(order, "")
        add_item(order, "Phone Case")

        self.assertEqual(order.items_summary, "your order + 1 more")

    def test_long_product_names_are_truncated_to_a_safe_length(self):
        order = make_order(self.user)
        add_item(order, "N" * 200)
        add_item(order, "Phone Case")

        summary = order.items_summary

        self.assertLessEqual(len(summary), Order.ITEMS_SUMMARY_MAX)
        self.assertTrue(summary.endswith(" + 1 more"))

    def test_the_complaint_order_choices_reuse_the_same_label(self):
        from apps.complaints.forms import OrderChoiceField

        order = make_order(self.user)
        add_item(order, "Wireless Earbuds")
        add_item(order, "Phone Case")

        field = OrderChoiceField(queryset=Order.objects.all())

        self.assertEqual(
            field.label_from_instance(order),
            "Wireless Earbuds + 1 more",
        )


class LoyaltyNotificationOrderLabelTests(TestCase):
    """
    Loyalty notifications and transaction descriptions must identify the
    order by product name instead of "Order #<id>".
    """

    def setUp(self):
        from apps.loyalty.models import LoyaltyTier as Tier
        from apps.loyalty.services import LoyaltyService

        self.service = LoyaltyService
        self.tier = Tier.objects.first() or Tier.objects.create(
            name="Bronze",
            minimum_points=0,
            points_multiplier=Decimal("1"),
        )
        self.user = User.objects.create_user(
            username="customer",
            email="customer@example.com",
            password="test-password-123",
        )
        # award_points/redeem_points require an existing account.
        self.service.get_or_create_account(self.user)

    def test_points_earned_notification_shows_the_product_name(self):
        order = make_order(self.user)
        add_item(order, "Wireless Earbuds")
        add_item(order, "Phone Case")

        self.service.award_points(
            user=self.user,
            points=150,
            transaction_type="PURCHASE",
            order=order,
        )

        message = Notification.objects.get(
            notif_type="POINTS_EARNED"
        ).message

        self.assertEqual(
            message,
            "You earned 150 loyalty points from "
            "Wireless Earbuds + 1 more. "
            "Your new balance is 150 points.",
        )
        self.assertNotIn(f"Order #{order.id}", message)

    def test_single_item_notification_shows_only_the_product_name(self):
        order = make_order(self.user)
        add_item(order, "Wireless Earbuds", quantity=3)

        self.service.award_points(
            user=self.user,
            points=150,
            transaction_type="PURCHASE",
            order=order,
        )

        message = Notification.objects.get(
            notif_type="POINTS_EARNED"
        ).message

        self.assertEqual(
            message,
            "You earned 150 loyalty points from Wireless Earbuds. "
            "Your new balance is 150 points.",
        )

    def test_points_earned_transaction_description_shows_the_product(self):
        order = make_order(self.user)
        add_item(order, "Wireless Earbuds")

        self.service.award_purchase_points(order)

        description = order.loyalty_transactions.get(
            transaction_type="PURCHASE"
        ).description

        self.assertEqual(
            description, "Points earned from Wireless Earbuds"
        )
        self.assertNotIn(f"Order #{order.id}", description)

    def test_notification_omits_the_label_when_there_is_no_order(self):
        self.service.award_points(
            user=self.user,
            points=50,
            transaction_type="REVIEW",
            description="Review bonus",
        )

        message = Notification.objects.get(
            notif_type="POINTS_EARNED"
        ).message

        self.assertEqual(
            message,
            "You earned 50 loyalty points. "
            "Your new balance is 50 points.",
        )
        self.assertNotIn("Order #", message)

    def test_points_redeemed_notification_shows_the_product_name(self):
        order = make_order(self.user)
        add_item(order, "Wireless Earbuds")
        add_item(order, "Phone Case")

        self.service.award_points(
            user=self.user,
            points=1000,
            transaction_type="PURCHASE",
            order=order,
        )
        self.service.redeem_points(
            user=self.user,
            points=500,
            order=order,
        )

        message = Notification.objects.get(
            notif_type="POINTS_REDEEMED"
        ).message

        self.assertIn("on Wireless Earbuds + 1 more", message)
        self.assertNotIn(f"Order #{order.id}", message)
