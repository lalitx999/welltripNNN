"""
Partner Studio across the 7 roles: who reaches which studio, edit/close of own items only,
and shipping paid OTOP orders.
"""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.accommodations.models import Accommodation, Room
from apps.accounts.models import MerchantApprovalStatus, MerchantProfile, User, UserRoles
from apps.bookings.models import Booking, BookingItem, BookingStatus, FulfillmentStatus
from apps.otop.models import OTOPProduct
from apps.services.models import FoodMenu, WellnessService

STUDIOS = {
    "homestay": "/accommodations/studio/",
    "restaurant": "/services/studio/restaurant/",
    "wellness": "/services/studio/wellness/",
    "otop": "/otop/studio/",
    "dashboard": "/accounts/portal/",
    "orders": "/accounts/portal/orders/",
}

# role -> studios it may open (everything else must be refused)
ACCESS = {
    UserRoles.TOURIST: set(),
    UserRoles.HOMESTAY_OWNER: {"homestay", "dashboard", "orders"},
    UserRoles.RESTAURANT_OWNER: {"restaurant", "dashboard", "orders"},
    UserRoles.WELLNESS_OWNER: {"wellness", "dashboard", "orders"},
    UserRoles.OTOP_OWNER: {"otop", "dashboard", "orders"},
    UserRoles.COMMUNITY_ADMIN: set(STUDIOS),
    UserRoles.SUPER_ADMIN: set(STUDIOS),
}


def make_user(role, email=None):
    user = User.objects.create_user(email=email or f"{role.lower()}@example.com", password="x", role=role)
    if role in (UserRoles.HOMESTAY_OWNER, UserRoles.RESTAURANT_OWNER, UserRoles.WELLNESS_OWNER, UserRoles.OTOP_OWNER):
        MerchantProfile.objects.create(user=user, business_name="ร้าน", status=MerchantApprovalStatus.APPROVED)
    return user


class SevenRoleAccessTestCase(TestCase):
    def test_each_role_reaches_only_its_studios(self):
        for role, allowed in ACCESS.items():
            user = make_user(role)
            self.client.force_login(user)
            for name, url in STUDIOS.items():
                status = self.client.get(url).status_code
                with self.subTest(role=role, studio=name):
                    if name in allowed:
                        # admins with no homestay in the system are sent back to the dashboard
                        self.assertIn(status, (200, 302) if name == "homestay" and role in (
                            UserRoles.COMMUNITY_ADMIN, UserRoles.SUPER_ADMIN) else (200,))
                    else:
                        self.assertIn(status, (302, 403))
            self.client.logout()
        self.assertFalse(Accommodation.objects.exclude(owner__role=UserRoles.HOMESTAY_OWNER).exists())


class OwnItemsOnlyTestCase(TestCase):
    def setUp(self):
        self.owner = make_user(UserRoles.OTOP_OWNER, "otop1@example.com")
        self.rival = make_user(UserRoles.OTOP_OWNER, "otop2@example.com")
        self.product = OTOPProduct.objects.create(owner=self.owner, name="ผ้าไหม", price=Decimal("500"), stock_quantity=5)

    def test_owner_edits_details_but_not_stock(self):
        self.client.force_login(self.owner)
        self.client.post(reverse("otop:product_edit", args=[self.product.id]), {
            "name": "ผ้าไหมลายลูกแก้ว", "category": self.product.category, "description": "", "price": "650",
            "stock_quantity": "999",
        })
        self.product.refresh_from_db()
        self.assertEqual(self.product.name, "ผ้าไหมลายลูกแก้ว")
        self.assertEqual(self.product.price, Decimal("650"))
        self.assertEqual(self.product.stock_quantity, 5)

    def test_other_partner_gets_404(self):
        self.client.force_login(self.rival)
        self.assertEqual(self.client.get(reverse("otop:product_edit", args=[self.product.id])).status_code, 404)
        self.assertEqual(self.client.post(reverse("otop:product_toggle", args=[self.product.id])).status_code, 404)
        self.product.refresh_from_db()
        self.assertTrue(self.product.is_active)

    def test_close_and_reopen_product(self):
        self.client.force_login(self.owner)
        self.client.post(reverse("otop:product_toggle", args=[self.product.id]))
        self.product.refresh_from_db()
        self.assertFalse(self.product.is_active)

    def test_spa_owner_closes_service_and_restaurant_owner_cannot(self):
        spa_owner = make_user(UserRoles.WELLNESS_OWNER)
        service = WellnessService.objects.create(owner=spa_owner, name="นวดประคบ", price=Decimal("300"))
        cook = make_user(UserRoles.RESTAURANT_OWNER)
        self.client.force_login(cook)
        self.assertEqual(self.client.post(reverse("services:item_toggle", args=["wellness", service.id])).status_code, 404)
        self.client.force_login(spa_owner)
        self.client.post(reverse("services:item_toggle", args=["wellness", service.id]))
        service.refresh_from_db()
        self.assertFalse(service.is_active)

    def test_food_edit(self):
        cook = make_user(UserRoles.RESTAURANT_OWNER)
        menu = FoodMenu.objects.create(owner=cook, name="ส้มตำ", price=Decimal("60"))
        self.client.force_login(cook)
        self.client.post(reverse("services:item_edit", args=["food", menu.id]), {
            "name": "ส้มตำสมุนไพร", "description": "", "price": "80",
            "wellness_category": menu.wellness_category, "calorie_estimate": "",
        })
        menu.refresh_from_db()
        self.assertEqual(menu.price, Decimal("80"))

    def test_wellness_studio_shows_add_service_fields(self):
        spa_owner = make_user(UserRoles.WELLNESS_OWNER)
        self.client.force_login(spa_owner)
        self.assertContains(self.client.get(STUDIOS["wellness"]), 'name="duration_minutes"')

    def test_room_edit_and_admin_room_create_needs_a_homestay(self):
        host = make_user(UserRoles.HOMESTAY_OWNER)
        acc = Accommodation.objects.create(owner=host, name="บ้านสวน")
        room = Room.objects.create(accommodation=acc, name="ห้องริมนา", base_price_per_night=Decimal("700"))
        self.client.force_login(host)
        self.client.post(reverse("accommodations:room_edit", args=[room.id]), {
            "name": "ห้องริมนา", "room_type": "Double", "capacity_people": 2,
            "base_price_per_night": "850", "total_rooms_count": 1,
        })
        room.refresh_from_db()
        self.assertEqual(room.base_price_per_night, Decimal("850"))

        admin = make_user(UserRoles.COMMUNITY_ADMIN)
        self.client.force_login(admin)
        self.client.post(reverse("accommodations:room_create"), {
            "name": "ห้องใหม่", "room_type": "Twin", "capacity_people": 2,
            "base_price_per_night": "500", "total_rooms_count": 1,
        })
        self.assertFalse(Room.objects.filter(name="ห้องใหม่").exists())


class OtopShippingTestCase(TestCase):
    def setUp(self):
        self.seller = make_user(UserRoles.OTOP_OWNER, "seller@example.com")
        self.customer = make_user(UserRoles.TOURIST, "buyer@example.com")
        self.booking = Booking.objects.create(
            customer=self.customer, total_amount=Decimal("250"), status=BookingStatus.CONFIRMED,
            shipping_address={"recipient_name": "ผู้รับ", "address_line": "1 ถ.หลัก", "district": "เมือง",
                              "province": "ศรีสะเกษ", "postal_code": "33000", "phone_number": "0800000000"},
        )
        self.item = BookingItem.objects.create(
            booking=self.booking, vendor=self.seller, item_type="OTOP", entity_id="1",
            item_title_snapshot="กาแฟ", unit_price_snapshot=Decimal("250"), subtotal=Decimal("250"),
        )

    def test_seller_ships_with_tracking_and_customer_sees_it(self):
        self.client.force_login(self.seller)
        page = self.client.get(reverse("accounts:portal_orders") + "?tab=to_ship")
        self.assertContains(page, "ผู้รับ")
        self.client.post(reverse("accounts:portal_fulfillment", args=[self.item.id]),
                         {"status": "SHIPPED", "tracking_number": "TH123"})
        self.item.refresh_from_db()
        self.assertEqual(self.item.fulfillment_status, FulfillmentStatus.SHIPPED)

        self.client.force_login(self.customer)
        self.assertContains(self.client.get(reverse("bookings:detail", args=[self.booking.id])), "TH123")

    def test_unpaid_order_cannot_be_shipped(self):
        Booking.objects.filter(pk=self.booking.pk).update(status=BookingStatus.AWAITING_PAYMENT)
        self.client.force_login(self.seller)
        self.client.post(reverse("accounts:portal_fulfillment", args=[self.item.id]),
                         {"status": "SHIPPED", "tracking_number": "TH123"})
        self.item.refresh_from_db()
        self.assertEqual(self.item.fulfillment_status, FulfillmentStatus.PENDING)

    def test_other_seller_cannot_ship(self):
        self.client.force_login(make_user(UserRoles.OTOP_OWNER, "other@example.com"))
        self.client.post(reverse("accounts:portal_fulfillment", args=[self.item.id]),
                         {"status": "SHIPPED", "tracking_number": "X"})
        self.item.refresh_from_db()
        self.assertEqual(self.item.fulfillment_status, FulfillmentStatus.PENDING)
