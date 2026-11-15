"""Catalog cards for the landing page and the signed-in /home dashboard."""
from django.db.models import Prefetch
from django.utils.translation import gettext as _

from apps.accommodations.models import Accommodation, AccommodationStatus, Room
from apps.otop.models import OTOPProduct
from apps.services.models import FoodMenu, WellnessService

PLACEHOLDER = '/static/images/catalog-placeholder.svg'


def _stay_price_and_image(stay):
    """Same answers as Accommodation.min_price_per_night / hero_image, from prefetched rooms."""
    rooms = stay.active_rooms  # active, cheapest first
    price = rooms[0].base_price_per_night if rooms else None
    image = None
    if rooms:
        first_room = min(rooms, key=lambda r: r.pk)
        images = list(first_room.images.all())
        img = next((i for i in images if i.is_cover), None) or (images[0] if images else None)
        image = img.image if img and img.image else None
    return price, image


def stay_cards(limit):
    rooms = Room.objects.filter(is_active=True).order_by('base_price_per_night').prefetch_related('images')
    stays = (
        Accommodation.objects.filter(status=AccommodationStatus.ACTIVE)
        .prefetch_related(Prefetch('rooms', queryset=rooms, to_attr='active_rooms'))[:limit]
    )
    cards = []
    for s in stays:
        price, image = _stay_price_and_image(s)
        cards.append({
            'title': s.name,
            'category': _("ที่พักชุมชน"),
            'location': f"{s.district}, {s.province}" if s.district else s.province,
            'price': f"฿{price:,.0f}" if price else None,
            'period': _("/ คืน"),
            'image': image.url if image else PLACEHOLDER,
            'href': f"/accommodations/{s.slug or s.id}/",
        })
    return cards


def spa_cards(limit):
    return [
        {
            'title': w.name,
            'category': _("สปาและกิจกรรม"),
            'location': _("ศรีสะเกษ"),
            'price': f"฿{w.price:,.0f}",
            'period': _("/ {duration_minutes} นาที").format(duration_minutes=w.duration_minutes) if w.duration_minutes else _("/ รอบ"),
            'image': w.image.url if w.image else PLACEHOLDER,
            'href': f"/services/detail/wellness/{w.id}/",
        }
        for w in WellnessService.objects.filter(is_active=True).order_by('-created_at')[:limit]
    ]


def food_cards(limit):
    return [
        {
            'title': f.name,
            'category': _("อาหารเพื่อสุขภาพ"),
            'location': _("ศรีสะเกษ"),
            'price': f"฿{f.price:,.0f}",
            'period': _("/ ชุด"),
            'image': f.image.url if f.image else PLACEHOLDER,
            'href': f"/services/detail/food/{f.id}/",
        }
        for f in FoodMenu.objects.filter(is_available=True).order_by('-created_at')[:limit]
    ]


def otop_cards(limit):
    return [
        {
            'title': p.name,
            'category': _("หัตถกรรม OTOP"),
            'location': _("ศรีสะเกษ"),
            'price': f"฿{p.price:,.0f}",
            'period': _("/ ชิ้น"),
            'image': p.image.url if p.image else PLACEHOLDER,
            'href': f"/otop/{p.id}/",
        }
        for p in OTOPProduct.objects.filter(is_active=True).order_by('-created_at')[:limit]
    ]
