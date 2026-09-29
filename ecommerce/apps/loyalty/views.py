from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .models import LoyaltyTier, LoyaltyTransaction
from .services import LoyaltyService


@login_required
def loyalty_dashboard(request):
    """
    Display the customer's loyalty dashboard.
    """

    account = LoyaltyService.get_or_create_account(
        request.user
    )

    current_tier = account.current_tier

    # ---------------------------------------------------------
    # FIND NEXT TIER
    # ---------------------------------------------------------

    next_tier = None

    if current_tier:
        next_tier = (
            account.current_tier.__class__.objects
            .filter(
                is_active=True,
                minimum_points__gt=account.lifetime_points_earned,
            )
            .order_by("minimum_points")
            .first()
        )

    # ---------------------------------------------------------
    # TIER PROGRESS
    # ---------------------------------------------------------

    progress_percentage = 100

    points_to_next_tier = 0

    if next_tier:
        current_minimum = current_tier.minimum_points
        next_minimum = next_tier.minimum_points

        tier_range = next_minimum - current_minimum

        earned_in_tier = (
            account.lifetime_points_earned
            - current_minimum
        )

        if tier_range > 0:
            progress_percentage = (
                earned_in_tier / tier_range
            ) * 100

        progress_percentage = min(
            max(progress_percentage, 0),
            100
        )

        points_to_next_tier = max(
            next_minimum
            - account.lifetime_points_earned,
            0
        )

    # ---------------------------------------------------------
    # RECENT LOYALTY ACTIVITY
    # ---------------------------------------------------------

    recent_transactions = (
        LoyaltyTransaction.objects
        .filter(account=account)
        .select_related("order")
        .order_by("-created_at")[:5]
    )

    context = {
        "account": account,
        "current_tier": current_tier,
        "next_tier": next_tier,
        "progress_percentage": round(
            progress_percentage,
            1
        ),
        "points_to_next_tier": points_to_next_tier,
        "recent_transactions": recent_transactions,
    }

    return render(
        request,
        "loyalty/dashboard.html",
        context
    )


@login_required
def loyalty_tiers(request):
    """
    Compare active loyalty tiers using the customer's lifetime earnings.
    """

    account = LoyaltyService.get_or_create_account(request.user)

    tiers = (
        LoyaltyTier.objects
        .filter(is_active=True)
        .order_by("minimum_points", "pk")
    )

    tier_cards = []
    next_tier = None
    points_to_next_tier = 0

    for tier in tiers:
        points_remaining = max(
            tier.minimum_points - account.lifetime_points_earned,
            0,
        )

        tier_cards.append({
            "tier": tier,
            "is_current": tier.pk == account.current_tier_id,
            "points_remaining": points_remaining,
        })

        if next_tier is None and points_remaining > 0:
            next_tier = tier
            points_to_next_tier = points_remaining

    context = {
        "account": account,
        "current_tier": account.current_tier,
        "tier_cards": tier_cards,
        "next_tier": next_tier,
        "points_to_next_tier": points_to_next_tier,
    }

    return render(request, "loyalty/tiers.html", context)


@login_required
def loyalty_rewards(request):
    """Explain the account's point value and checkout redemption rules."""

    account = LoyaltyService.get_or_create_account(request.user)

    # Checkout only accepts whole 100-point blocks.
    redeemable_points = (account.available_points // 100) * 100
    remainder_points = account.available_points - redeemable_points

    redeemable_value = (
        LoyaltyService.calculate_reward_value(redeemable_points)
        if redeemable_points
        else Decimal("0.00")
    )

    redemption_examples = [
        {
            "points": points,
            "value": LoyaltyService.calculate_reward_value(points),
        }
        for points in (100, 500, 1000)
    ]

    context = {
        "account": account,
        "redeemable_points": redeemable_points,
        "remainder_points": remainder_points,
        "redeemable_value": redeemable_value,
        "redemption_examples": redemption_examples,
    }

    return render(request, "loyalty/rewards.html", context)
