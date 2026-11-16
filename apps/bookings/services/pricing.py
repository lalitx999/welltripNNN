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

from apps.accommodations.models import AccommodationStatus, Room, RoomCooling, RoomPricingCalendar
from apps.core.pricing import customer_price
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
    stay_total: Decimal | None = None  # rooms: whole stay for one house/room, guests included
    cooling: str = ""  # rooms: FAN or AIR, as chosen by the guest
    guests: int = 0  # rooms: guest count (prices per person multiply by it)
    error: str = ""


def parse_date(value):
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def room_option_title(room, cooling, guests):
    parts = [str(RoomCooling(cooling).label)]
    if room.is_per_person:
        parts.append(_("{count} คน").format(count=guests))
    return f"{room.name} ({room.accommodation.name}) · " + " · ".join(parts)


def resolve_cart_item(item_type, entity_id, check_in="", check_out="", cooling="", guests=None):
    """
    Look up the real title and customer price (platform fee included) for a cart
    entry, or explain why it can't be added.
    """
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
            # Same nightly prices checkout will charge: special calendar price, else the base price
            calendar = {
                c.date: c for c in RoomPricingCalendar.objects.filter(room=room, date__in=stay_dates(start, nights))
            }
            full = [d for d, c in calendar.items() if c.available_count <= 0]
            if full:
                return ResolvedItem(error=_("ห้องนี้เต็มแล้วในวันที่ {date}").format(date=min(full).strftime("%d/%m/%Y")))
            options = room.cooling_options()
            cooling = cooling if cooling in options else options[0]
            guest_count = parse_guests(guests, room)
            if isinstance(guest_count, str):
                return ResolvedItem(error=guest_count)
            units = guest_count if room.is_per_person else 1
            nightly = [
                customer_price(room.owner_nightly_price(cooling, calendar[d].price if d in calendar else None))
                for d in stay_dates(start, nights)
            ]
            return ResolvedItem(
                title=room_option_title(room, cooling, guest_count),
                unit_price=nightly[0] * units,
                date=start.isoformat(),
                nights=nights,
                stay_total=sum(nightly) * units,
                cooling=cooling,
                guests=guest_count,
            )

        if item_type == BookingItemType.FOOD:
            menu = FoodMenu.objects.get(id=entity_id, is_available=True)
            return ResolvedItem(title=menu.name, unit_price=menu.customer_price)

        if item_type == BookingItemType.WELLNESS:
            if str(entity_id).isdigit():
                slot = WellnessTimeSlot.objects.select_related("service").get(
                    id=int(entity_id), service__is_active=True, date__gte=timezone.localdate(),
                )
                if slot.capacity_available <= 0:
                    return ResolvedItem(error=_("รอบเวลานี้เต็มแล้ว"))
                return ResolvedItem(
                    title=f"{slot.service.name} [{slot.start_time:%H:%M}-{slot.end_time:%H:%M}]",
                    unit_price=slot.service.customer_price,
                    date=slot.date.isoformat(),
                )
            service = WellnessService.objects.get(id=entity_id, is_active=True)
            return ResolvedItem(title=service.name, unit_price=service.customer_price)

        if item_type == BookingItemType.OTOP:
            product = OTOPProduct.objects.get(id=entity_id, is_active=True)
            if product.stock_quantity <= 0:
                return ResolvedItem(error=_("สินค้า '{name}' หมดชั่วคราว").format(name=product.name))
            return ResolvedItem(title=product.name, unit_price=product.customer_price)
    except (Room.DoesNotExist, FoodMenu.DoesNotExist, WellnessService.DoesNotExist,
            WellnessTimeSlot.DoesNotExist, OTOPProduct.DoesNotExist, ValidationError, ValueError):
        pass

    return ResolvedItem(error=_("ไม่พบรายการนี้ หรือรายการปิดให้บริการแล้ว"))


def parse_guests(value, room):
    """Guest count for a house: 1..capacity. Returns an error message instead when out of range."""
    try:
        count = int(value) if value not in (None, "") else (1 if room.is_per_person else room.capacity_people)
    except (TypeError, ValueError):
        count = 1
    if count < 1:
        count = 1
    if count > room.capacity_people:
        return _("{name} พักได้สูงสุด {count} คน").format(name=room.name, count=room.capacity_people)
    return count


def cart_line_total(item):
    """Line total for a session cart entry: unit price x quantity x nights (rooms)."""
    if item.get("stay_total"):
        return Decimal(str(item["stay_total"])) * int(item.get("quantity", 1))
    nights = max(1, int(item.get("nights", 1) or 1))
    return Decimal(str(item.get("price", 0))) * int(item.get("quantity", 1)) * nights


def stay_dates(start: date, nights: int):
    """Every night of a stay, starting at check-in."""
    return [start + timedelta(days=offset) for offset in range(max(1, nights))]
