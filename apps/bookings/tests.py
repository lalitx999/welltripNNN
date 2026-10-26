import datetime
from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User, UserRoles
from apps.accommodations.models import Accommodation, Room, RoomPricingCalendar
from apps.services.models import WellnessService, WellnessTimeSlot
from apps.otop.models import OTOPProduct, OTOPCategory
from apps.bookings.models import Booking, BookingItem, BookingStatus, BookingItemType
from apps.bookings.services.checkout import (
    process_checkout,
    cancel_and_restore_expired_bookings,
    StockUnavailableError,
)


class ConcurrencyBookingSecurityTestCase(TestCase):
    """
    Security Test Suite for EP 5:
    Verifies Concurrency Control (select_for_update), Zero-Trust stock locking,
    15-minute TTL auto-restoration, and IDOR protection.
    """

    def setUp(self):
        self.client = Client()
        self.password = "StrongPassword123!"

        # Create Tourist 1 & 2
        self.tourist1 = User.objects.create_user(
            email="tourist1@example.com",
            password=self.password,
            role=UserRoles.TOURIST,
        )
        self.tourist2 = User.objects.create_user(
            email="tourist2@example.com",
            password=self.password,
            role=UserRoles.TOURIST,
        )

        # Create Merchant
        self.merchant = User.objects.create_user(
            email="merchant@example.com",
            password=self.password,
            role=UserRoles.OTOP_OWNER,
        )

        # Create OTOP Product with initial stock of 3
        self.product = OTOPProduct.objects.create(
            owner=self.merchant,
            name="ผ้าพันคอมะเกลือ",
            category=OTOPCategory.TEXTILE,
            price=Decimal("500.00"),
            stock_quantity=3,
        )

        # Create Homestay & Room
        self.accommodation = Accommodation.objects.create(
            owner=self.merchant,
            name="โฮมสเตย์ศรีสะเกษ",
        )
        self.room = Room.objects.create(
            accommodation=self.accommodation,
            name="ห้องชมดาว",
            base_price_per_night=Decimal("1000.00"),
            total_rooms_count=1,
        )
        self.booking_date = datetime.date(2026, 11, 20)
        self.calendar = RoomPricingCalendar.objects.create(
            room=self.room,
            date=self.booking_date,
            price=Decimal("1000.00"),
            available_count=1,
        )

    def test_process_checkout_locks_stock_and_prevents_overbooking(self):
        """
        WHY: Concurrency control via select_for_update prevents double-selling.
        """
        cart = [{
            "item_type": BookingItemType.OTOP,
            "entity_id": str(self.product.id),
            "quantity": 2,
        }]

        # Tourist 1 orders 2 units (out of 3)
        booking1 = process_checkout(self.tourist1, cart)
        self.assertEqual(booking1.total_amount, Decimal("1000.00"))

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 1)

        # Tourist 2 attempts to order 2 units (only 1 left) -> must fail!
        with self.assertRaises(StockUnavailableError):
            process_checkout(self.tourist2, cart)

        # Stock must still be 1 (transaction rolled back safely)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 1)

    def test_process_checkout_locks_room_calendar(self):
        """Verifies room availability is locked per night."""
        cart = [{
            "item_type": BookingItemType.ROOM,
            "entity_id": str(self.room.id),
            "date": "2026-11-20",
            "quantity": 1,
        }]

        # Tourist 1 books room
        booking = process_checkout(self.tourist1, cart)
        self.assertEqual(booking.status, BookingStatus.AWAITING_PAYMENT)

        self.calendar.refresh_from_db()
        self.assertEqual(self.calendar.available_count, 0)

        # Tourist 2 attempts to book same room on same date -> fails!
        with self.assertRaises(StockUnavailableError):
            process_checkout(self.tourist2, cart)

    def test_15_minute_expiry_restores_inventories(self):
        """
        WHY: Unpaid bookings must release locks after 15 minutes.
        """
        cart = [{
            "item_type": BookingItemType.OTOP,
            "entity_id": str(self.product.id),
            "quantity": 2,
        }]
        booking = process_checkout(self.tourist1, cart)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 1)

        # Artificially expire the booking
        booking.expires_at = timezone.now() - datetime.timedelta(minutes=1)
        booking.save(update_fields=["expires_at"])

        # Run expiry engine
        restored = cancel_and_restore_expired_bookings()
        self.assertEqual(restored, 1)

        booking.refresh_from_db()
        self.assertEqual(booking.status, BookingStatus.PAYMENT_EXPIRED)

        # Stock is restored to 3!
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 3)

    def test_booking_detail_idor_defense(self):
        """
        WHY: Tourist 2 must never see Tourist 1's booking details.
        """
        cart = [{
            "item_type": BookingItemType.OTOP,
            "entity_id": str(self.product.id),
            "quantity": 1,
        }]
        booking = process_checkout(self.tourist1, cart)

        # Tourist 2 tries to view Tourist 1's booking
        self.client.force_login(self.tourist2)
        url = reverse('bookings:detail', kwargs={'booking_id': booking.id})

        response = self.client.get(url)
        # Blocked and redirected to own bookings
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('bookings:my_bookings'), response.url)
