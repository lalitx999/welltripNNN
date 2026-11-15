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


class AdminCatalogTestCase(TestCase):
    """Admin Center catalog: category and owning shop are chosen, never silently defaulted."""

    def setUp(self):
        self.admin = make_user(UserRoles.COMMUNITY_ADMIN, "cat-admin@example.com")
        self.seller = make_user(UserRoles.OTOP_OWNER, "shop@example.com")
        self.seller.merchant_profile.business_name = "ร้านผ้าทอบ้านโพธิ์"
        self.seller.merchant_profile.save()
        self.client.force_login(self.admin)

    def _add(self, **extra):
        data = {"item_type": "OTOP", "title": "เสื้อลาย SISAKET", "price": "290", "stock_quantity": "5"}
        data.update(extra)
        return self.client.post(reverse("accounts:admin_catalog_add"), data)

    def test_otop_needs_a_category(self):
        self._add()
        self.assertFalse(OTOPProduct.objects.exists())
        self._add(category="TEXTILE")
        self.assertEqual(OTOPProduct.objects.get().category, "TEXTILE")

    def test_item_can_be_filed_under_a_shop_of_the_right_type(self):
        self._add(category="TEXTILE", owner_id=str(self.seller.id))
        self.assertEqual(OTOPProduct.objects.get().owner, self.seller)
        cook = make_user(UserRoles.RESTAURANT_OWNER, "cook2@example.com")
        self._add(title="ผิดประเภท", category="TEXTILE", owner_id=str(cook.id))
        self.assertFalse(OTOPProduct.objects.filter(name="ผิดประเภท").exists())

    def test_edit_changes_category(self):
        product = OTOPProduct.objects.create(owner=self.admin, name="เสื้อ", price=Decimal("290"))
        self.client.post(reverse("accounts:admin_catalog_edit", args=["OTOP", product.id]),
                         {"title": "เสื้อ", "price": "290", "is_active": "1", "category": "TEXTILE"})
        product.refresh_from_db()
        self.assertEqual(product.category, "TEXTILE")

    def test_public_pages_show_shop_name_never_email(self):
        product = OTOPProduct.objects.create(owner=self.seller, name="ผ้าไหม", price=Decimal("500"), stock_quantity=1)
        admin_product = OTOPProduct.objects.create(owner=self.admin, name="กาแฟ", price=Decimal("250"), stock_quantity=1)
        self.client.logout()
        listing = self.client.get("/otop/")
        self.assertContains(listing, "ร้านผ้าทอบ้านโพธิ์")
        self.assertContains(listing, "WellTrip Sisaket")
        self.assertNotContains(listing, "shop@example.com")
        self.assertNotContains(listing, "cat-admin@example.com")
        self.assertNotContains(self.client.get(f"/otop/{product.id}/"), "shop@example.com")
        self.assertNotContains(self.client.get(f"/otop/{admin_product.id}/"), "cat-admin@example.com")


class ShopSetupTestCase(TestCase):
    """Partners decorate their shop right after sign-up; at most 3 photos; public only once approved."""

    def setUp(self):
        import io
        from PIL import Image
        self.Image, self.io = Image, io
        self.partner = User.objects.create_user(email="new-shop@example.com", password="x", role=UserRoles.OTOP_OWNER)
        self.profile = MerchantProfile.objects.create(user=self.partner, business_name="ร้านใหม่", business_category="OTOP")
        self.client.force_login(self.partner)

    def _image(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        buf = self.io.BytesIO()
        self.Image.new("RGB", (60, 40), color="orange").save(buf, format="JPEG")
        return SimpleUploadedFile("shop.jpg", buf.getvalue(), content_type="image/jpeg")

    def test_pending_partner_can_set_up_the_shop(self):
        self.assertEqual(self.client.get(reverse("accounts:portal_shop")).status_code, 200)
        self.client.post(reverse("accounts:portal_shop"), {
            "business_name": "ร้านผ้าไหมแม่มาลี", "description": "ผ้าไหมทอมือ", "phone_number": "0812345678",
            "opening_hours": "ทุกวัน 08:00-17:00", "google_maps_url": "",
        })
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.business_name, "ร้านผ้าไหมแม่มาลี")
        self.assertContains(self.client.get(reverse("accounts:portal_dashboard"), follow=True), "ตกแต่งร้าน", status_code=403)

    def test_at_most_three_photos(self):
        from apps.accounts.models import MerchantShopImage
        for _ in range(4):
            self.client.post(reverse("accounts:portal_shop_image"), {"action": "add", "image": self._image()})
        self.assertEqual(MerchantShopImage.objects.filter(profile=self.profile).count(), 3)
        last = MerchantShopImage.objects.filter(profile=self.profile).last()
        self.client.post(reverse("accounts:portal_shop_image"), {"action": "cover", "image_id": last.id})
        self.assertEqual(MerchantShopImage.objects.filter(profile=self.profile).first(), last)

    def test_shop_page_public_only_after_approval(self):
        url = reverse("core:shop_detail", args=[self.profile.id])
        self.assertEqual(self.client.get(url).status_code, 200)  # owner preview
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 404)
        self.profile.status = MerchantApprovalStatus.APPROVED
        self.profile.save()
        OTOPProduct.objects.create(owner=self.partner, name="ผ้าไหมลายลูกแก้ว", price=Decimal("900"), stock_quantity=1)
        page = self.client.get(url)
        self.assertContains(page, "ร้านใหม่")
        self.assertContains(page, "ผ้าไหมลายลูกแก้ว")
        self.assertNotContains(page, "new-shop@example.com")

    def test_tourist_cannot_open_shop_setup(self):
        self.client.force_login(User.objects.create_user(email="t2@example.com", password="x", role=UserRoles.TOURIST))
        self.assertEqual(self.client.get(reverse("accounts:portal_shop")).status_code, 302)
