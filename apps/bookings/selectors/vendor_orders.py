"""Order lines a partner sold, for Partner Studio."""
from apps.accounts.permissions import scope_to_owner
from apps.bookings.models import BookingItem, BookingItemType, BookingStatus, FulfillmentStatus

ORDER_TABS = ("all", "awaiting", "confirmed", "to_ship")


def vendor_order_items(user, tab="all"):
    items = scope_to_owner(
        BookingItem.objects.select_related("booking__customer", "vendor"), user, "vendor"
    ).order_by("-booking__created_at", "id")
    if tab == "awaiting":
        items = items.filter(booking__status=BookingStatus.AWAITING_PAYMENT)
    elif tab == "confirmed":
        items = items.filter(booking__status__in=[BookingStatus.CONFIRMED, BookingStatus.COMPLETED])
    elif tab == "to_ship":
        items = items.filter(
            item_type=BookingItemType.OTOP,
            booking__status=BookingStatus.CONFIRMED,
            fulfillment_status=FulfillmentStatus.PENDING,
        )
    return items


def to_ship_count(user):
    return vendor_order_items(user, "to_ship").count()
