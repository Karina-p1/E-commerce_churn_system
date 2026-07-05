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

    code = models.CharField(max_length=50, unique=True)

    discount_type = models.CharField(
        max_length=20,
        choices=DISCOUNT_TYPE_CHOICES,
        default='PERCENTAGE'
    )

    discount_value = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    min_order_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    max_uses = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Leave blank for unlimited uses."
    )

    used_count = models.PositiveIntegerField(default=0)

    is_active = models.BooleanField(default=True)

    valid_from = models.DateTimeField(null=True, blank=True)
    valid_until = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.code

    def is_valid(self, order_amount=None):
        """
        Returns (is_valid: bool, error_message: str)
        """
        now = timezone.now()

        if not self.is_active:
            return False, "This coupon is no longer active."

        if self.valid_from and now < self.valid_from:
            return False, "This coupon is not yet valid."

        if self.valid_until and now > self.valid_until:
            return False, "This coupon has expired."

        if self.max_uses is not None and self.used_count >= self.max_uses:
            return False, "This coupon has reached its usage limit."

        if order_amount is not None and Decimal(order_amount) < self.min_order_amount:
            return False, f"Minimum order amount for this coupon is Rs.{self.min_order_amount}."

        return True, ""

    def calculate_discount(self, amount):
        amount = Decimal(amount)

        if self.discount_type == 'PERCENTAGE':
            discount = (amount * self.discount_value) / Decimal('100')
        else:
            discount = self.discount_value

        if discount > amount:
            discount = amount

        return discount.quantize(Decimal('0.01'))


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
        ("REFUND_PENDING", "Refund Pending"),
        ("REFUNDED", "Refunded"),
    ]
    
    REFUND_STATUS_CHOICES = [
        ("NONE", "Not Required"),
        ("PENDING", "Pending"),
        ("REFUNDED", "Refunded"),
    ]

    refund_status = models.CharField(
        max_length=20,
        choices=REFUND_STATUS_CHOICES,
        default="NONE",
    )

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

    # ==========================
    # Coupon / Discount
    # ==========================

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
    def final_price(self):
        """Amount the customer actually pays — total_price minus coupon discount."""
        discount = self.discount_amount or Decimal('0')
        return self.total_price - discount
    
    @property
    def can_cancel(self):
        return self.status in [
            "pending",
            "processing",
        ]
    
    @property
    def order_number(self):
        return f"ORD-{self.id:06d}"


    @property
    def preview_items(self):
        return self.items.all()[:2]


    @property
    def remaining_items(self):
        count = self.items.count()
        return max(0, count - 2)
    
    def set_status(self, new_status, note=None, changed_by=None):
        self.status = new_status

        update_fields = ["status", "updated_at"]

        revenue_needs_update = False

        if new_status == "delivered":
            if (
                self.payment_method == "COD"
                and self.payment_status == "UNPAID"
            ):
                self.payment_status = "PAID"
                self.paid_at = timezone.now()

                update_fields.extend(["payment_status", "paid_at"])

                revenue_needs_update = True

        if new_status == "cancelled":
            self.cancelled_at = timezone.now()
            update_fields.append("cancelled_at")

        self.save(update_fields=update_fields)

        self.status_history.create(
            status=new_status,
            note=note,
            changed_by=changed_by,
        )

        if revenue_needs_update:
            from django.db import transaction
            from apps.analytics.tasks import paid_order_created

            transaction.on_commit(
                lambda: paid_order_created.delay(self.id)
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