from decimal import Decimal
from django.db import models
from django.conf import settings
from apps.products.models import Product
from django.utils import timezone


class Coupon(models.Model):
    DISCOUNT_TYPE_CHOICES = [
        ('PERCENTAGE', 'Percentage'),
        ('FLAT', 'Flat Amount'),
    ]

    COUPON_TYPE_CHOICES = [
        ('STANDARD', 'Standard'),
        ('FIRST_ORDER', 'First Order Only'),
        ('MIN_QUANTITY', 'Minimum Quantity'),
        ('BUY_X_GET_Y', 'Buy X Get Y'),
    ]

    code = models.CharField(max_length=50, unique=True)

    coupon_type = models.CharField(
        max_length=20,
        choices=COUPON_TYPE_CHOICES,
        default='STANDARD'
    )

    discount_type = models.CharField(
        max_length=20,
        choices=DISCOUNT_TYPE_CHOICES,
        default='PERCENTAGE'
    )

    discount_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text=(
            "Percentage or flat amount. "
            "Ignored for BUY_X_GET_Y "
            "(use get_discount_percent instead)."
        )
    )
    
    # Shipping discount
    shipping_fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text=(
            "Shipping discount provided by this coupon. "
            "Use 0 for no shipping discount. "
            "The discount cannot exceed the shipping fee."
        )
    )

    min_order_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    # Minimum loyalty tier required to use this coupon.
    # Example:
    # Gold coupon → Gold and Platinum customers can use it.
    minimum_loyalty_tier = models.ForeignKey(
        "loyalty.LoyaltyTier",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="coupons",
        help_text="Minimum loyalty tier required to use this coupon."
    )

    # ── MIN_QUANTITY fields ───────────────────────────────────────────
    min_quantity = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=(
            "MIN_QUANTITY type only: "
            "minimum total cart items required."
        )
    )

    # ── BUY_X_GET_Y fields ─────────────────────────────────────────────
    buy_quantity = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=(
            "BUY_X_GET_Y type only: "
            "number of items the customer must buy."
        )
    )

    get_quantity = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=(
            "BUY_X_GET_Y type only: "
            "number of additional items that get discounted."
        )
    )

    get_discount_percent = models.PositiveIntegerField(
        default=100,
        help_text=(
            "BUY_X_GET_Y type only: discount % applied to "
            "the 'get' items. 100 = free."
        )
    )

    max_uses = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Leave blank for unlimited uses."
    )

    used_count = models.PositiveIntegerField(default=0)

    is_active = models.BooleanField(default=True)

    valid_from = models.DateTimeField(
        null=True,
        blank=True
    )

    valid_until = models.DateTimeField(
        null=True,
        blank=True,
        help_text=(
            "Setting this also marks the coupon as a "
            "limited-time offer for notification purposes."
        )
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.code

    @property
    def is_limited_time_offer(self):
        return bool(self.valid_until)

    def is_valid(self, order_amount=None, user=None, cart_quantity=None):
        """
        Returns:
            (is_valid: bool, error_message: str)

        order_amount:
            Cart subtotal, used for minimum-order validation
            and discount calculation.

        user:
            Used for FIRST_ORDER and loyalty-tier eligibility.

        cart_quantity:
            Total item count in cart, required for
            MIN_QUANTITY / BUY_X_GET_Y.
        """

        now = timezone.now()

        # ── Basic coupon validity ──────────────────────────────────────

        if not self.is_active:
            return False, "This coupon is no longer active."

        if self.valid_from and now < self.valid_from:
            return False, "This coupon is not yet valid."

        if self.valid_until and now > self.valid_until:
            return False, "This coupon has expired."

        if (
            self.max_uses is not None
            and self.used_count >= self.max_uses
        ):
            return False, "This coupon has reached its usage limit."

        # ── Minimum order amount ───────────────────────────────────────

        if (
            order_amount is not None
            and Decimal(order_amount) < self.min_order_amount
        ):
            return False, (
                f"Minimum order amount for this coupon is "
                f"Rs.{self.min_order_amount}."
            )

        # ── First-order eligibility ───────────────────────────────────

        if self.coupon_type == 'FIRST_ORDER':
            if user is None or not user.is_authenticated:
                return False, "This coupon requires an account."

            has_prior_order = (
                Order.objects
                .filter(user=user)
                .exclude(status='cancelled')
                .exists()
            )

            if has_prior_order:
                return False, (
                    "This coupon is valid only on your first order."
                )

        # ── Minimum quantity eligibility ──────────────────────────────

        if self.coupon_type == 'MIN_QUANTITY':
            required = self.min_quantity or 0

            if (
                cart_quantity is None
                or cart_quantity < required
            ):
                return False, (
                    f"This coupon requires at least "
                    f"{required} item(s) in your cart."
                )

        # ── Buy X Get Y eligibility ───────────────────────────────────

        if self.coupon_type == 'BUY_X_GET_Y':
            required = (
                (self.buy_quantity or 0)
                + (self.get_quantity or 0)
            )

            if (
                cart_quantity is None
                or cart_quantity < required
            ):
                return False, (
                    f"This coupon requires at least "
                    f"{required} item(s) in your cart "
                    f"(buy {self.buy_quantity}, "
                    f"get {self.get_quantity})."
                )

        # ── Loyalty-tier eligibility ──────────────────────────────────
        #
        # If the coupon requires a loyalty tier, the customer
        # must be authenticated and have a tier at or above
        # the required tier.
        #
        # Example:
        # Gold coupon:
        #   Bronze  -> rejected
        #   Silver  -> rejected
        #   Gold    -> allowed
        #   Platinum -> allowed

        if self.minimum_loyalty_tier:
            if user is None or not user.is_authenticated:
                return False, (
                    "This coupon requires a loyalty account."
                )

            from apps.loyalty.services import LoyaltyService

            loyalty_account = (
                LoyaltyService.get_or_create_account(user)
            )

            current_tier = loyalty_account.current_tier
            required_tier = self.minimum_loyalty_tier

            if current_tier is None:
                return False, (
                    "This coupon requires a higher loyalty tier."
                )

            if (
                current_tier.minimum_points
                < required_tier.minimum_points
            ):
                return False, (
                    "This coupon requires a higher loyalty tier."
                )

        return True, "Coupon is valid."

    def calculate_discount(self, amount, cart_items=None):
        """
        amount:
            Cart subtotal (Decimal-able).

        cart_items:
            List of:
                {
                    'price': Decimal,
                    'quantity': int
                }

            Required for BUY_X_GET_Y.
        """

        amount = Decimal(amount)

        if self.coupon_type == 'BUY_X_GET_Y':
            if not cart_items:
                return Decimal('0.00')

            return self._calculate_buy_x_get_y_discount(
                cart_items
            )

        if self.discount_type == 'PERCENTAGE':
            discount = (
                amount * self.discount_value
            ) / Decimal('100')
        else:
            discount = self.discount_value

        if discount > amount:
            discount = amount

        return discount.quantize(
            Decimal('0.01')
        )

    def _calculate_buy_x_get_y_discount(self, cart_items):
        """
        Flattens cart items into individual unit prices,
        sorts cheapest-first, and discounts the eligible
        cheapest units.

        Example:
            Buy 2 Get 1
            6 items in cart
            → 2 complete groups
            → 2 cheapest items receive the discount.
        """

        units = []

        for item in cart_items:
            units.extend(
                [Decimal(item['price'])] * item['quantity']
            )

        if not units:
            return Decimal('0.00')

        units.sort()

        group_size = (
            (self.buy_quantity or 0)
            + (self.get_quantity or 0)
        )

        if group_size <= 0:
            return Decimal('0.00')

        eligible_groups = len(units) // group_size

        discount_units_count = (
            eligible_groups
            * (self.get_quantity or 0)
        )

        if discount_units_count <= 0:
            return Decimal('0.00')

        discount_total = (
            sum(units[:discount_units_count])
            * (
                Decimal(self.get_discount_percent)
                / Decimal('100')
            )
        )

        return discount_total.quantize(
            Decimal('0.01')
        )

class Cart(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='cart'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Cart of {self.user.username}"

    @property
    def total_price(self):
        return sum(item.subtotal for item in self.items.all())

    @property
    def total_items(self):
        return sum(item.quantity for item in self.items.all())


class CartItem(models.Model):
    cart = models.ForeignKey(
        Cart,
        on_delete=models.CASCADE,
        related_name='items'
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE
    )
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        unique_together = ('cart', 'product')

    def __str__(self):
        return f"{self.product.name} x {self.quantity}"

    @property
    def subtotal(self):
        return self.product.effective_price * self.quantity

class Order(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('shipped', 'Shipped'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
    ]

    PAYMENT_STATUS_CHOICES = [
        ('UNPAID', 'Unpaid'),
        ('INITIATED', 'Payment Initiated'),
        ('PAID', 'Paid'),
        ('FAILED', 'Failed'),
        ("REFUND_PENDING", "Refund Requested"),
        ("REFUNDED", "Refunded"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='orders'
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )
    REFUND_STATUS_CHOICES = [
    ('NONE', 'No Refund'),
    ('PENDING', 'Refund Pending'),
    ('COMPLETED', 'Refund Completed'),
    ('REJECTED', 'Refund Rejected'),
]

    refund_status = models.CharField(
    max_length=20,
    choices=REFUND_STATUS_CHOICES,
    default='NONE',
)
    CANCEL_REASON_CHOICES = (
        ("mistake", "Ordered by mistake"),
        ("cheaper", "Found cheaper elsewhere"),
        ("delivery", "Delivery takes too long"),
        ("changed", "Changed my mind"),
        ("payment", "Payment issue"),
        ("other", "Other"),
    )

    cancel_reason = models.CharField(
        max_length=20,
        choices=CANCEL_REASON_CHOICES,
        blank=True,
        null=True,
    )

    cancel_note = models.TextField(
        blank=True,
        null=True,
    )

    cancelled_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    payment_status = models.CharField(
        max_length=20,
        choices=PAYMENT_STATUS_CHOICES,
        default='UNPAID'
    )

    payment_method = models.CharField(
        max_length=30,
        default='ESEWA'
    )

    transaction_uuid = models.CharField(
        max_length=100,
        unique=True,
        null=True,
        blank=True
    )

    esewa_ref_id = models.CharField(
        max_length=100,
        null=True,
        blank=True
    )

    paid_at = models.DateTimeField(
        null=True,
        blank=True
    )

    total_price = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    coupon = models.ForeignKey(
        Coupon,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='orders'
    )

    discount_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )
    
    shipping_fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("150.00"),
        help_text="Shipping fee charged for this order."
    )
    
    loyalty_points_redeemed = models.PositiveIntegerField(
        default=0,
        help_text="Number of loyalty points redeemed for this order."
    )

    loyalty_discount_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Discount amount obtained from loyalty points."
    )

    # ==========================
    # Delivery Address Snapshot
    # ==========================

    delivery_label = models.CharField(
        max_length=30,
        blank=True
    )

    delivery_full_name = models.CharField(
        max_length=150,
        blank=True
    )

    delivery_phone = models.CharField(
        max_length=20,
        blank=True
    )

    delivery_province = models.CharField(
        max_length=100,
        blank=True
    )

    delivery_district = models.CharField(
        max_length=100,
        blank=True
    )

    delivery_city = models.CharField(
        max_length=100,
        blank=True
    )

    delivery_ward = models.CharField(
        max_length=20,
        blank=True
    )

    delivery_street = models.CharField(
        max_length=255,
        blank=True
    )

    delivery_landmark = models.CharField(
        max_length=255,
        blank=True
    )

    delivery_latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True
    )

    delivery_longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        
    @property
    def can_cancel(self):
        return self.status in [
            "pending",
            "processing",
        ]
    
    def set_status(self, new_status, note=None, changed_by=None):
        self.status = new_status
        update_fields = ['status', 'updated_at']
        if new_status == 'cancelled':
            self.cancelled_at = timezone.now()
            update_fields.append('cancelled_at')
        self.save(update_fields=update_fields)

        self.status_history.create(
            status=new_status,
            note=note,
            changed_by=changed_by,
        )

    def __str__(self):
        return f"Order #{self.id} by {self.user.username}"

class OrderItem(models.Model):
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='items'
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.SET_NULL,
        null=True
    )
    product_name = models.CharField(max_length=300)
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )
    quantity = models.PositiveIntegerField()

    def __str__(self):
        return f"{self.product_name} x {self.quantity}"

    @property
    def subtotal(self):
        return self.price * self.quantity
    
class OrderStatusHistory(models.Model):
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='status_history'
    )
    status = models.CharField(
        max_length=20,
        choices=Order.STATUS_CHOICES
    )
    note = models.CharField(
        max_length=255,
        blank=True,
        null=True
    )
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        verbose_name_plural = "Order status histories"

    def __str__(self):
        return f"Order #{self.order_id} -> {self.status} at {self.created_at:%Y-%m-%d %H:%M}"
    
class RefundRequest(models.Model):

    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("APPROVED", "Approved"),
        ("REJECTED", "Rejected"),
        ("COMPLETED", "Completed"),
    ]

    REASON_CHOICES = [
        ("DAMAGED", "Damaged product"),
        ("WRONG_ITEM", "Wrong item received"),
        ("ORDERED_BY_MISTAKE", "Ordered by mistake"),
        ("BETTER_PRICE", "Found a better price"),
        ("DELAYED", "Delivery taking too long"),
        ("CHANGED_MIND", "Changed my mind"),
        ("OTHER", "Other"),
    ]

    order = models.OneToOneField(
        Order,
        on_delete=models.CASCADE,
        related_name="refund_request"
    )

    reason = models.CharField(
        max_length=30,
        choices=REASON_CHOICES
    )

    other_reason = models.TextField(
        blank=True
    )

    bank_name = models.CharField(
        max_length=120
    )

    account_holder = models.CharField(
        max_length=120
    )

    account_number = models.CharField(
        max_length=50
    )

    branch = models.CharField(
        max_length=120,
        blank=True
    )

    phone = models.CharField(
        max_length=20,
        blank=True
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="PENDING"
    )

    admin_note = models.TextField(
        blank=True
    )

    requested_at = models.DateTimeField(
        auto_now_add=True
    )

    processed_at = models.DateTimeField(
        null=True,
        blank=True
    )

    def __str__(self):
        return f"Refund - Order #{self.order.id}"