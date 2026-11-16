import io
import shutil
import tempfile
from datetime import timedelta
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from apps.accommodations.models import (
    Accommodation, AccommodationStatus, Room, RoomCooling, RoomImage, RoomPricingCalendar, RoomPricingMode,
)
from apps.accounts.models import MerchantApprovalStatus, MerchantProfile, User, UserRoles
from apps.bookings.services.checkout import StockUnavailableError, process_checkout
from apps.bookings.services.pricing import resolve_cart_item

MEDIA = tempfile.mkdtemp()


def png(name="house.png"):
    buffer = io.BytesIO()
    Image.new("RGB", (40, 30), (200, 120, 40)).save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


class HouseSetup(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="enterprise@example.com", password="x", role=UserRoles.HOMESTAY_OWNER)
        MerchantProfile.objects.create(user=self.owner, business_name="วิสาหกิจบ้านโนน", status=MerchantApprovalStatus.APPROVED)
        self.tourist = User.objects.create_user(email="guest@example.com", password="x", role=UserRoles.TOURIST)
        self.acc = Accommodation.objects.create(owner=self.owner, name="วิสาหกิจบ้านโนน", status=AccommodationStatus.ACTIVE)
        self.both = Room.objects.create(
            accommodation=self.acc, name="บ้านแม่บุญมา", cooling=RoomCooling.BOTH, capacity_people=4,
            base_price_per_night=Decimal("500"), air_price_per_night=Decimal("700"),
        )
        self.per_person = Room.objects.create(
            accommodation=self.acc, name="บ้านพ่อสม", cooling=RoomCooling.FAN, capacity_people=15,
            pricing_mode=RoomPricingMode.PER_PERSON, base_price_per_night=Decimal("200"),
        )
        self.check_in = timezone.localdate() + timedelta(days=5)
        self.check_out = self.check_in + timedelta(days=2)

    def cart_line(self, room, cooling="", guests=None):
        resolved = resolve_cart_item("ROOM", str(room.id), self.check_in.isoformat(), self.check_out.isoformat(), cooling, guests)
        self.assertEqual(resolved.error, "")
        return {
            "item_type": "ROOM", "entity_id": str(room.id), "quantity": 1, "date": resolved.date,
            "nights": resolved.nights, "stay_total": str(resolved.stay_total),
            "cooling": resolved.cooling, "guests": resolved.guests,
        }, resolved


class HousePricingTests(HouseSetup):
    def test_fan_and_air_prices_include_the_fee(self):
        _, fan = self.cart_line(self.both, "FAN")
        _, air = self.cart_line(self.both, "AIR")
        self.assertEqual(fan.stay_total, Decimal("1050"))  # 2 nights x 525
        self.assertEqual(air.stay_total, Decimal("1470"))  # 2 nights x 735
        self.assertIn("ห้องแอร์", air.title)

    def test_per_person_price_multiplies_by_guests(self):
        _, resolved = self.cart_line(self.per_person, guests=6)
        self.assertEqual(resolved.stay_total, Decimal("2520"))  # 210 x 6 guests x 2 nights

    def test_guests_over_capacity_are_refused(self):
        resolved = resolve_cart_item("ROOM", str(self.both.id), self.check_in.isoformat(), self.check_out.isoformat(), "FAN", 5)
        self.assertIn("สูงสุด 4 คน", resolved.error)

    def test_fan_only_house_ignores_an_air_request(self):
        _, resolved = self.cart_line(self.per_person, "AIR", 1)
        self.assertEqual(resolved.cooling, "FAN")

    def test_special_calendar_price_keeps_the_air_surcharge(self):
        RoomPricingCalendar.objects.create(room=self.both, date=self.check_in, price=Decimal("600"), available_count=1)
        _, air = self.cart_line(self.both, "AIR")
        # night 1: (600 + 200) x 1.05 = 840 ; night 2: 700 x 1.05 = 735
        self.assertEqual(air.stay_total, Decimal("1575"))

    def test_checkout_matches_the_cart_and_records_the_choice(self):
        line, resolved = self.cart_line(self.per_person, guests=3)
        booking = process_checkout(self.tourist, [line])
        self.assertEqual(booking.total_amount, resolved.stay_total)
        item = booking.items.first()
        self.assertEqual(item.booking_metadata["guests"], 3)
        self.assertEqual(item.booking_metadata["cooling"], "FAN")
        self.assertEqual(item.owner_amount, Decimal("600.00"))  # 200 x 3 guests
        self.assertEqual(item.platform_fee, Decimal("30.00"))

    def test_checkout_rechecks_capacity(self):
        line, _ = self.cart_line(self.both, "FAN", 2)
        line["guests"] = 9
        with self.assertRaises(StockUnavailableError):
            process_checkout(self.tourist, [line])


@override_settings(MEDIA_ROOT=MEDIA)
class HouseStudioTests(HouseSetup):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def test_one_account_adds_many_houses(self):
        self.client.force_login(self.owner)
        for name in ("บ้านลุงเปลี่ยน", "บ้านป้าแดง"):
            self.client.post(reverse("accommodations:room_create"), {
                "accommodation_id": str(self.acc.id), "name": name, "cooling": "AIR", "capacity_people": 3,
                "pricing_mode": "PER_HOUSE", "base_price_per_night": "650", "total_rooms_count": 1,
            })
        self.assertEqual(self.acc.rooms.count(), 4)

    def test_both_needs_an_air_price(self):
        self.client.force_login(self.owner)
        self.client.post(reverse("accommodations:room_create"), {
            "accommodation_id": str(self.acc.id), "name": "บ้านไม่ครบ", "cooling": "BOTH", "capacity_people": 3,
            "pricing_mode": "PER_HOUSE", "base_price_per_night": "500", "total_rooms_count": 1,
        })
        self.assertFalse(self.acc.rooms.filter(name="บ้านไม่ครบ").exists())

    def test_a_house_has_at_most_three_photos(self):
        self.client.force_login(self.owner)
        url = reverse("accommodations:room_image_add", args=[self.both.id])
        for i in range(4):
            self.client.post(url, {"image": png(f"{i}.png")})
        self.assertEqual(RoomImage.objects.filter(room=self.both).count(), Room.MAX_IMAGES)

    def test_profile_photo_is_the_listing_photo(self):
        self.client.force_login(self.owner)
        self.client.post(f"{reverse('accommodations:homestay_studio')}?acc_id={self.acc.id}", {
            "accommodation_id": str(self.acc.id), "name": self.acc.name, "province": "ศรีสะเกษ",
            "profile_image": png("profile.png"),
        })
        self.acc.refresh_from_db()
        self.assertTrue(self.acc.profile_image)
        self.assertEqual(self.acc.hero_image, self.acc.profile_image)

    def test_detail_page_lists_every_house_with_customer_prices(self):
        page = self.client.get(reverse("accommodations:detail", args=[self.acc.slug]))
        self.assertContains(page, "บ้านแม่บุญมา")
        self.assertContains(page, "บ้านพ่อสม")
        self.assertContains(page, "฿525")  # fan 500 + 5%
        self.assertContains(page, "฿735")  # air 700 + 5%
        self.assertContains(page, "รายละเอียด") if self.acc.description else None
        self.assertContains(page, 'id="houses-data"')
