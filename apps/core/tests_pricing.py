from datetime import timedelta
from decimal import Decimal

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import User, UserRoles
from apps.bookings.services.checkout import process_checkout
from apps.core.pricing import customer_price, platform_fee, round_baht
from apps.otop.models import OTOPProduct
from apps.services.models import FoodMenu, WellnessService


class FeeRoundingTests(TestCase):
    def test_client_examples(self):
        self.assertEqual(customer_price(Decimal("100")), Decimal("105"))
        self.assertEqual(customer_price(Decimal("95")), Decimal("100"))  # 99.75 rounds up

    def test_half_rounds_up_and_below_half_rounds_down(self):
        self.assertEqual(round_baht(Decimal("99.5")), Decimal("100"))
        self.assertEqual(round_baht(Decimal("99.49")), Decimal("99"))
        self.assertEqual(customer_price(Decimal("10")), Decimal("11"))  # 10.5 -> 11
        self.assertEqual(customer_price(Decimal("9")), Decimal("9"))  # 9.45 -> 9

    def test_prices_are_whole_baht(self):
        for owner in ("1", "33.33", "250", "999.99", "1234"):
            price = customer_price(Decimal(owner))
            self.assertEqual(price, price.to_integral_value())

    def test_fee_is_the_difference(self):
        self.assertEqual(platform_fee(Decimal("95")), Decimal("5"))
        self.assertEqual(platform_fee(Decimal("100")), Decimal("5"))

    @override_settings(PLATFORM_FEE_PERCENT=10)
    def test_rate_comes_from_settings(self):
        self.assertEqual(customer_price(Decimal("100")), Decimal("110"))


class FeeAtCheckoutTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="fee_owner@example.com", password="x", role=UserRoles.OTOP_OWNER)
        self.tourist = User.objects.create_user(email="fee_tourist@example.com", password="x", role=UserRoles.TOURIST)

    def test_every_partner_price_gets_the_fee_and_the_split_is_recorded(self):
        product = OTOPProduct.objects.create(owner=self.owner, name="ผ้าไหม", price=Decimal("95"), stock_quantity=5)
        food = FoodMenu.objects.create(owner=self.owner, name="ส้มตำ", price=Decimal("80"))
        spa = WellnessService.objects.create(owner=self.owner, name="นวด", price=Decimal("300"))
        booking = process_checkout(self.tourist, [
            {"item_type": "OTOP", "entity_id": str(product.id), "quantity": 2},
            {"item_type": "FOOD", "entity_id": str(food.id), "quantity": 1},
            {"item_type": "WELLNESS", "entity_id": str(spa.id), "quantity": 1},
        ])
        # 2 x 100 + 84 + 315
        self.assertEqual(booking.total_amount, Decimal("599.00"))
        lines = {i.item_type: i for i in booking.items.all()}
        self.assertEqual(lines["OTOP"].unit_price_snapshot, Decimal("100"))
        self.assertEqual(lines["OTOP"].owner_amount, Decimal("190.00"))
        self.assertEqual(lines["OTOP"].platform_fee, Decimal("10.00"))
        self.assertEqual(sum(i.owner_amount + i.platform_fee for i in booking.items.all()), booking.total_amount)

    def test_shipping_has_no_fee(self):
        product = OTOPProduct.objects.create(owner=self.owner, name="กาแฟ", price=Decimal("200"), stock_quantity=5)
        booking = process_checkout(
            self.tourist, [{"item_type": "OTOP", "entity_id": str(product.id), "quantity": 1}],
            shipping_fee=Decimal("50.00"),
        )
        self.assertEqual(booking.total_amount, Decimal("260.00"))  # 210 + 50

    def test_public_pages_show_the_customer_price(self):
        product = OTOPProduct.objects.create(owner=self.owner, name="ตะกร้าสาน", price=Decimal("95"), stock_quantity=5)
        page = self.client.get(f"/otop/{product.id}/")
        self.assertContains(page, "฿100")
        self.assertNotContains(page, "฿95")
