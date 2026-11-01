"""
Server-side pricing for cart items.

The cart lives in the session, and anything posted from a page (title, price,
night count) can be edited by the visitor. Every cart entry is therefore built
from the database here; the checkout service recomputes prices again when the
booking is created.
"""
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.accommodations.models import AccommodationStatus, Room
from apps.bookings.models import BookingItemType
from apps.otop.models import OTOPProduct
from apps.services.models import FoodMenu, WellnessService, WellnessTimeSlot
from django.utils.translation import gettext as _

MAX_NIGHTS = 30


@dataclass
class ResolvedItem:
    title: str = ""
    unit_price: Decimal = Decimal("0.00")
    date: str = ""
    nights: int = 1
    error: str = ""


def parse_date(value):
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def resolve_cart_item(item_type, entity_id, check_in="", check_out=""):
    """Look up the real title and unit price for a cart entry, or explain why it can't be added."""
    try:
        if item_type == BookingItemType.ROOM:
            room = Room.objects.select_related("accommodation").get(
                id=entity_id, is_active=True, accommodation__status=AccommodationStatus.ACTIVE,
            )
            start, end = parse_date(check_in), parse_date(check_out)
            if not start or not end or end <= start:
                return ResolvedItem(error=_("กรุณาเลือกวันเช็คอินและเช็คเอาท์ให้ถูกต้อง"))
            if start < timezone.localdate():
                return ResolvedItem(error=_("วันเช็คอินต้องไม่ใช่วันที่ผ่านมาแล้ว"))
            nights = (end - start).days
            if nights > MAX_NIGHTS:
                return ResolvedItem(error=_("จองได้สูงสุด {MAX_NIGHTS} คืนต่อครั้ง").format(MAX_NIGHTS=MAX_NIGHTS))
            return ResolvedItem(
                title=f"{room.name} ({room.accommodation.name})",
                unit_price=room.base_price_per_night,
                date=start.isoformat(),
                nights=nights,
            )

        if item_type == BookingItemType.FOOD:
            menu = FoodMenu.objects.get(id=entity_id, is_available=True)
            return ResolvedItem(title=menu.name, unit_price=menu.price)

        if item_type == BookingItemType.WELLNESS:
            if str(entity_id).isdigit():
                slot = WellnessTimeSlot.objects.select_related("service").get(id=int(entity_id), service__is_active=True)
                return ResolvedItem(
                    title=f"{slot.service.name} [{slot.start_time:%H:%M}-{slot.end_time:%H:%M}]",
                    unit_price=slot.service.price,
                    date=slot.date.isoformat(),
                )
            service = WellnessService.objects.get(id=entity_id, is_active=True)
            return ResolvedItem(title=service.name, unit_price=service.price)

        if item_type == BookingItemType.OTOP:
            product = OTOPProduct.objects.get(id=entity_id, is_active=True)
            if product.stock_quantity <= 0:
                return ResolvedItem(error=_("สินค้า '{name}' หมดชั่วคราว").format(name=product.name))
            return ResolvedItem(title=product.name, unit_price=product.price)
    except (Room.DoesNotExist, FoodMenu.DoesNotExist, WellnessService.DoesNotExist,
            WellnessTimeSlot.DoesNotExist, OTOPProduct.DoesNotExist, ValidationError, ValueError):
        pass

    return ResolvedItem(error=_("ไม่พบรายการนี้ หรือรายการปิดให้บริการแล้ว"))


def cart_line_total(item):
    """Line total for a session cart entry: unit price x quantity x nights (rooms)."""
    nights = max(1, int(item.get("nights", 1) or 1))
    return Decimal(str(item.get("price", 0))) * int(item.get("quantity", 1)) * nights


def stay_dates(start: date, nights: int):
    """Every night of a stay, starting at check-in."""
    return [start + timedelta(days=offset) for offset in range(max(1, nights))]
