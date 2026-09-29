from decimal import Decimal, ROUND_DOWN

from django.db import transaction

from apps.orders.models import Order
from apps.notifications.models import Notification

from .models import (
    LoyaltyAccount,
    LoyaltyTier,
    LoyaltyTransaction,
)

class LoyaltyService:
    """
    Central service for all loyalty-related operations.

    All point changes should go through this service so that:
    - balances stay consistent
    - transactions are recorded
    - tier upgrades happen automatically
    - duplicate logic is avoided
    """

    BASE_AMOUNT_PER_POINT = Decimal("10")
    POINTS_PER_RUPEE_REWARD = Decimal("0.5")

    @staticmethod
    def _create_notification(user, notif_type, title, message):
        """Create a customer notification for a completed loyalty event."""
        return Notification.objects.create(
            recipient=user,
            notif_type=notif_type,
            title=title,
            message=message,
        )

    @staticmethod
    def get_or_create_account(user):
        """
        Get the user's loyalty account.

        If the account does not exist, create it with the
        Bronze tier.
        """

        account = LoyaltyAccount.objects.filter(user=user).first()

        if account:
            return account

        bronze = (
            LoyaltyTier.objects
            .filter(
                is_active=True,
                minimum_points=0
            )
            .order_by("minimum_points")
            .first()
        )

        if not bronze:
            raise ValueError(
                "No default loyalty tier exists. "
                "Create the Bronze tier first."
            )

        account = LoyaltyAccount.objects.create(
            user=user,
            current_tier=bronze,
        )

        return account
    
    @staticmethod
    def get_shipping_fee(user):
        """
        Return the delivery fee based on the user's loyalty tier.
        Gold and Platinum members get free shipping.
        """
        standard_shipping_fee = Decimal("150.00")

        account = LoyaltyService.get_or_create_account(user)

        if (
            account.current_tier
            and account.current_tier.free_shipping
        ):
            return Decimal("0.00")

        return standard_shipping_fee

    @staticmethod
    def calculate_purchase_points(amount, tier):
        """
        Calculate loyalty points earned from a purchase.

        Base rule:
            Rs. 10 = 1 point

        The customer's tier multiplier is then applied.

        Example:
            Rs. 1,000 at Bronze
            = 100 points

            Rs. 1,000 at Gold
            = 125 points
        """

        amount = Decimal(str(amount))

        if amount <= 0:
            return 0

        base_points = amount / LoyaltyService.BASE_AMOUNT_PER_POINT

        multiplier = tier.points_multiplier

        final_points = base_points * multiplier

        # Loyalty points are whole numbers.
        # We round DOWN so we never accidentally award more
        # points than the purchase qualifies for.
        final_points = final_points.quantize(
            Decimal("1"),
            rounding=ROUND_DOWN
        )

        return max(int(final_points), 0)
    
    @staticmethod
    @transaction.atomic
    def award_purchase_points(order):
        """
        Award loyalty points for a successfully paid order.

        Purchase points are awarded only once per order.
        """

        # Prevent duplicate purchase rewards.
        already_awarded = LoyaltyTransaction.objects.filter(
            order=order,
            transaction_type="PURCHASE"
        ).exists()

        if already_awarded:
            return LoyaltyAccount.objects.get(
                user=order.user
            )

        user = order.user

        account = LoyaltyService.get_or_create_account(user)

        # Ensure the account has a tier.
        if not account.current_tier:
            tier = LoyaltyService.get_tier_for_points(
                account.lifetime_points_earned
            )

            if not tier:
                raise ValueError(
                    "No loyalty tier is configured."
                )

            account.current_tier = tier

            account.save(
                update_fields=[
                    "current_tier",
                    "updated_at",
                ]
            )

        eligible_amount = order.total_price

        points = LoyaltyService.calculate_purchase_points(
            eligible_amount,
            account.current_tier
        )

        if points <= 0:
            return account

        return LoyaltyService.award_points(
            user=user,
            points=points,
            transaction_type="PURCHASE",
            description=f"Points earned from Order #{order.id}",
            order=order,
        )
    
    @staticmethod
    @transaction.atomic
    def award_first_purchase_bonus(user, order):
        account = (
            LoyaltyAccount.objects
            .select_for_update()
            .get(user=user)
        )

        # Prevent the first-purchase reward from being awarded twice
        already_awarded = LoyaltyTransaction.objects.filter(
            account=account,
            transaction_type="FIRST_PURCHASE",
        ).exists()

        if already_awarded:
            return account

        # Only award this if this is actually the customer's first
        # successful paid order.
        previous_paid_order_exists = (
            Order.objects
            .filter(
                user=user,
                payment_status="PAID",
            )
            .exclude(id=order.id)
            .exists()
        )

        if previous_paid_order_exists:
            return account

        return LoyaltyService.award_points(
            user=user,
            points=200,
            transaction_type="FIRST_PURCHASE",
            description=f"First purchase bonus for Order #{order.id}",
            order=order,
        )
        
    @staticmethod
    @transaction.atomic
    def award_review_points(user, order, product):
        """
        Award 50 loyalty points for a verified purchase review.

        Requirements:
        - Order must belong to the user.
        - Order must be PAID.
        - Product must exist in the order.
        - Review reward can only be awarded once for the order.
        """

        account = LoyaltyService.get_or_create_account(user)

        account = (
            LoyaltyAccount.objects
            .select_for_update()
            .get(pk=account.pk)
        )

        # Prevent duplicate review rewards for the same order.
        already_awarded = LoyaltyTransaction.objects.filter(
            account=account,
            order=order,
            transaction_type="REVIEW",
        ).exists()

        if already_awarded:
            return account

        # Make sure the order belongs to this customer.
        if order.user_id != user.id:
            raise ValueError("This order does not belong to the customer.")

        # Only completed/paid purchases qualify.
        if order.payment_status != "PAID":
            raise ValueError(
                "Review points can only be awarded for paid orders."
            )

        # Verify that the customer actually purchased this product.
        from apps.orders.models import OrderItem

        purchased_product = OrderItem.objects.filter(
            order=order,
            product=product,
        ).exists()

        if not purchased_product:
            raise ValueError(
                "Review points require a verified purchase of this product."
            )

        return LoyaltyService.award_points(
            user=user,
            points=50,
            transaction_type="REVIEW",
            description=f"Verified purchase review for {product.name}",
            order=order,
        )
    
    @staticmethod
    def get_tier_for_points(points):
        """
        Find the highest tier the customer qualifies for
        based on lifetime points earned.
        """

        return (
            LoyaltyTier.objects
            .filter(
                is_active=True,
                minimum_points__lte=points
            )
            .order_by("-minimum_points")
            .first()
        )

    @staticmethod
    @transaction.atomic
    def award_points(
        user,
        points,
        transaction_type,
        description="",
        order=None,
    ):
        """
        Award points to a customer.

        Updates:
        - available points
        - lifetime points earned
        - current tier
        - transaction history
        """

        if points <= 0:
            raise ValueError(
                "Awarded points must be greater than zero."
            )

        # Lock ONLY the loyalty account.
        account = (
            LoyaltyAccount.objects
            .select_for_update()
            .get(user=user)
        )

        # Remember the tier before this earning event so we can
        # notify only when the customer actually moves up.
        previous_tier = account.current_tier

        # Ensure the account has a tier.
        if not account.current_tier_id:
            tier = LoyaltyService.get_tier_for_points(
                account.lifetime_points_earned
            )

            if not tier:
                raise ValueError(
                    "No loyalty tier is configured."
                )

            account.current_tier = tier

        account.available_points += points
        account.lifetime_points_earned += points

        # Recalculate tier after earning points.
        new_tier = LoyaltyService.get_tier_for_points(
            account.lifetime_points_earned
        )

        if new_tier:
            account.current_tier = new_tier

        account.save(
            update_fields=[
                "available_points",
                "lifetime_points_earned",
                "current_tier",
                "updated_at",
            ]
        )

        LoyaltyTransaction.objects.create(
            account=account,
            transaction_type=transaction_type,
            points=points,
            balance_after=account.available_points,
            description=description,
            order=order,
        )

        order_text = f" from Order #{order.id}" if order else ""
        LoyaltyService._create_notification(
            user=user,
            notif_type="POINTS_EARNED",
            title=f"{points} loyalty points earned",
            message=(
                f"You earned {points} loyalty points{order_text}. "
                f"Your new balance is {account.available_points} points."
            ),
        )

        if (
            new_tier
            and previous_tier
            and new_tier.id != previous_tier.id
            and new_tier.minimum_points > previous_tier.minimum_points
        ):
            LoyaltyService._create_notification(
                user=user,
                notif_type="TIER_UPGRADE",
                title=f"Welcome to {new_tier.name}!",
                message=(
                    f"You've reached the {new_tier.name} loyalty tier "
                    f"and unlocked your new benefits."
                ),
            )

        return account

    @staticmethod
    def get_redeemable_points(user, requested_points):
        account = (
            LoyaltyAccount.objects
            .select_for_update()
            .get(user=user)
        )

        requested_points = int(requested_points)

        if requested_points <= 0:
            raise ValueError("Points must be greater than zero.")

        if requested_points > account.available_points:
            raise ValueError("Insufficient loyalty points.")

        return requested_points

    @staticmethod
    @transaction.atomic
    def redeem_points(
        user,
        points,
        description="Points redeemed",
        order=None
    ):
        if points <= 0:
            raise ValueError(
                "Redeemed points must be greater than zero."
            )

        # Lock the loyalty account so two Celery executions
        # cannot modify the balance at the same time.
        account = (
            LoyaltyAccount.objects
            .select_for_update()
            .get(user=user)
        )

        # ---------------------------------------------------------
        # IDEMPOTENCY CHECK
        # ---------------------------------------------------------
        # If this order has already had its loyalty points
        # redeemed, do nothing.
        if order is not None:
            already_redeemed = LoyaltyTransaction.objects.filter(
                account=account,
                order=order,
                transaction_type="REDEMPTION",
            ).exists()

            if already_redeemed:
                return account

        # ---------------------------------------------------------
        # CHECK AVAILABLE BALANCE
        # ---------------------------------------------------------
        if account.available_points < points:
            raise ValueError(
                "Insufficient loyalty points."
            )

        # ---------------------------------------------------------
        # DEDUCT POINTS
        # ---------------------------------------------------------
        account.available_points -= points
        account.lifetime_points_redeemed += points

        account.save(
            update_fields=[
                "available_points",
                "lifetime_points_redeemed",
                "updated_at",
            ]
        )

        # ---------------------------------------------------------
        # CREATE TRANSACTION
        # ---------------------------------------------------------
        LoyaltyTransaction.objects.create(
            account=account,
            transaction_type="REDEMPTION",
            points=-points,
            balance_after=account.available_points,
            description=description,
            order=order,
        )

        reward_value = LoyaltyService.calculate_reward_value(points)
        order_text = f" on Order #{order.id}" if order else ""
        LoyaltyService._create_notification(
            user=user,
            notif_type="POINTS_REDEEMED",
            title=f"{points} loyalty points redeemed",
            message=(
                f"{points} loyalty points were redeemed{order_text}, "
                f"saving you Rs. {reward_value:.2f}. "
                f"Your new balance is {account.available_points} points."
            ),
        )

        return account

    @staticmethod
    @transaction.atomic
    def reverse_points(
        user,
        points,
        description="Points reversed",
        order=None,
    ):
        """
        Reverse previously awarded loyalty points.

        Used for refunds/cancellations.

        Rules:
        - A reversal can only happen once for an order.
        - The loyalty account is locked during the operation.
        - Available points cannot go below zero.
        - Lifetime earned points are reduced by the refunded
        points so the refunded purchase no longer contributes
        toward the customer's tier.
        - A REFUND_REVERSAL transaction is always recorded.
        """

        if points <= 0:
            raise ValueError(
                "Reversed points must be greater than zero."
            )

        # ---------------------------------------------------------
        # LOCK LOYALTY ACCOUNT
        # ---------------------------------------------------------
        account = (
            LoyaltyAccount.objects
            .select_for_update()
            .get(user=user)
        )

        # ---------------------------------------------------------
        # IDEMPOTENCY CHECK
        # ---------------------------------------------------------
        # Prevent the same refund/cancellation from reversing
        # loyalty points more than once.
        if order is not None:
            already_reversed = LoyaltyTransaction.objects.filter(
                account=account,
                order=order,
                transaction_type="REFUND_REVERSAL",
            ).exists()

            if already_reversed:
                return account

        # ---------------------------------------------------------
        # CALCULATE ACTUAL AVAILABLE POINTS TO REMOVE
        # ---------------------------------------------------------
        points_to_remove_from_balance = min(
            points,
            account.available_points,
        )

        # ---------------------------------------------------------
        # UPDATE AVAILABLE POINTS
        # ---------------------------------------------------------
        account.available_points -= points_to_remove_from_balance

        # ---------------------------------------------------------
        # UPDATE LIFETIME EARNED POINTS
        # ---------------------------------------------------------
        account.lifetime_points_earned = max(
            0,
            account.lifetime_points_earned - points,
        )

        # ---------------------------------------------------------
        # RECALCULATE TIER
        # ---------------------------------------------------------
        new_tier = LoyaltyService.get_tier_for_points(
            account.lifetime_points_earned
        )

        if new_tier:
            account.current_tier = new_tier

        # ---------------------------------------------------------
        # SAVE ACCOUNT
        # ---------------------------------------------------------
        account.save(
            update_fields=[
                "available_points",
                "lifetime_points_earned",
                "current_tier",
                "updated_at",
            ]
        )

        # ---------------------------------------------------------
        # RECORD REVERSAL TRANSACTION
        # ---------------------------------------------------------
        LoyaltyTransaction.objects.create(
            account=account,
            transaction_type="REFUND_REVERSAL",
            points=-points,
            balance_after=account.available_points,
            description=description,
            order=order,
        )

        return account

    @staticmethod
    @transaction.atomic
    def reverse_order_points(order, description=None):
        """
        Reverse all loyalty effects associated with an order.

        Reverses:
        - PURCHASE points
        - FIRST_PURCHASE bonus
        - Restores redeemed points

        Review points are NOT reversed because the review is a
        separate customer action and is not automatically invalidated
        by an order refund/cancellation.
        """

        if not order:
            raise ValueError(
                "An order is required for point reversal."
            )

        account = (
            LoyaltyAccount.objects
            .select_for_update()
            .get(user=order.user)
        )

        if description is None:
            description = (
                f"Loyalty points reversed for Order #{order.id}"
            )

        # ---------------------------------------------------------
        # 1. REVERSE PURCHASE + FIRST PURCHASE POINTS
        # ---------------------------------------------------------

        earned_transactions = (
            LoyaltyTransaction.objects
            .filter(
                account=account,
                order=order,
                transaction_type__in=[
                    "PURCHASE",
                    "FIRST_PURCHASE",
                ],
                points__gt=0,
            )
        )

        total_points_earned = sum(
            transaction.points
            for transaction in earned_transactions
        )

        # Check whether the earned points have already been reversed.
        reversal_exists = LoyaltyTransaction.objects.filter(
            account=account,
            order=order,
            transaction_type="REFUND_REVERSAL",
        ).exists()

        if total_points_earned > 0 and not reversal_exists:

            points_to_remove = min(
                total_points_earned,
                account.available_points,
            )

            account.available_points -= points_to_remove

            account.lifetime_points_earned = max(
                0,
                account.lifetime_points_earned
                - total_points_earned,
            )

            # Recalculate tier after removing earned points.
            new_tier = LoyaltyService.get_tier_for_points(
                account.lifetime_points_earned
            )

            if new_tier:
                account.current_tier = new_tier

            account.save(
                update_fields=[
                    "available_points",
                    "lifetime_points_earned",
                    "current_tier",
                    "updated_at",
                ]
            )

            LoyaltyTransaction.objects.create(
                account=account,
                transaction_type="REFUND_REVERSAL",
                points=-total_points_earned,
                balance_after=account.available_points,
                description=description,
                order=order,
            )

        # ---------------------------------------------------------
        # 2. RESTORE REDEEMED POINTS
        # ---------------------------------------------------------

        redemption = (
            LoyaltyTransaction.objects
            .filter(
                account=account,
                order=order,
                transaction_type="REDEMPTION",
                points__lt=0,
            )
            .first()
        )

        redemption_reversal_exists = LoyaltyTransaction.objects.filter(
            account=account,
            order=order,
            transaction_type="REDEMPTION_REVERSAL",
        ).exists()

        if (
            redemption
            and not redemption_reversal_exists
        ):
            redeemed_points = abs(redemption.points)

            account.available_points += redeemed_points

            account.save(
                update_fields=[
                    "available_points",
                    "updated_at",
                ]
            )

            LoyaltyTransaction.objects.create(
                account=account,
                transaction_type="REDEMPTION_REVERSAL",
                points=redeemed_points,
                balance_after=account.available_points,
                description=(
                    f"Redeemed loyalty points restored "
                    f"for Order #{order.id}"
                ),
                order=order,
            )

            LoyaltyService._create_notification(
                user=order.user,
                notif_type="POINTS_RESTORED",
                title=f"{redeemed_points} loyalty points restored",
                message=(
                    f"{redeemed_points} redeemed loyalty points from "
                    f"Order #{order.id} were restored. Your balance is "
                    f"now {account.available_points} points."
                ),
            )

        return account

    @staticmethod
    def calculate_reward_value(points):
        """
        Convert loyalty points into their monetary value.

        100 points = Rs. 50

        Therefore:
            1 point = Rs. 0.50
        """

        if points <= 0:
            return Decimal("0.00")

        return (
            Decimal(points)
            * LoyaltyService.POINTS_PER_RUPEE_REWARD
        )