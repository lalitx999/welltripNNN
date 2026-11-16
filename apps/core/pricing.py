"""
Platform fee: what the customer pays for a price set by a partner.

Every partner price (room night, wellness service, food menu, OTOP product)
is shown and charged with the platform fee added (5% unless PLATFORM_FEE_PERCENT
says otherwise), as whole baht: .5 and above rounds up, below .5 rounds down.

    owner price 100 -> customer 105
    owner price  95 -> 99.75 -> customer 100

The fee is worked out per unit price, before multiplying by nights, guests or
quantity, so the price on a page always multiplies to the cart total. Shipping
is set by the platform and has no fee.
"""
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings

WHOLE_BAHT = Decimal("1")


def fee_rate() -> Decimal:
    return Decimal(str(getattr(settings, "PLATFORM_FEE_PERCENT", 5))) / Decimal("100")


def round_baht(amount) -> Decimal:
    """Whole baht, half up (99.5 -> 100, 99.49 -> 99)."""
    return Decimal(str(amount)).quantize(WHOLE_BAHT, rounding=ROUND_HALF_UP)


def customer_price(owner_price):
    """Price the customer sees and pays for one unit of a partner price."""
    if owner_price is None or owner_price == "":
        return None
    return round_baht(Decimal(str(owner_price)) * (Decimal("1") + fee_rate()))


def platform_fee(owner_price) -> Decimal:
    """Platform share of one unit: customer price minus the partner's price."""
    if owner_price is None or owner_price == "":
        return Decimal("0")
    return customer_price(owner_price) - Decimal(str(owner_price))


def owner_price_for(customer_amount) -> Decimal:
    """Approximate partner price for a customer amount (used for price filters only)."""
    return Decimal(str(customer_amount)) / (Decimal("1") + fee_rate())
