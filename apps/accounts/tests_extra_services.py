"""
"เปิดบริการเพิ่มเติม" (a homestay that also sells OTOP / spa / food) and the partner's
payout bank account.
"""
from decimal import Decimal

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.forms import PayoutAccountForm
from apps.accounts.models import AuditLog, MerchantApprovalStatus, MerchantProfile, User, UserRoles
from apps.otop.models import OTOPProduct

ADMIN_EMAIL = "ops@example.com"


def make_partner(role=UserRoles.HOMESTAY_OWNER, category="HOMESTAY", status=MerchantApprovalStatus.APPROVED,
                 email="host@example.com", extras=None):
    user = User.objects.create_user(email=email, password="x", role=role)
    MerchantProfile.objects.create(user=user, business_name="บ้านสวนศรีสะเกษ", business_category=category,
                                   status=status, extra_services=extras or [])
    return user


@override_settings(ADMIN_EMAIL=ADMIN_EMAIL)
class ExtraServicesTestCase(TestCase):
    def setUp(self):
        self.host = make_partner()
        self.client.force_login(self.host)

    def _save(self, *services):
        return self.client.post(reverse("accounts:portal_services"), {"services": list(services)})

    def test_homestay_cannot_reach_otop_studio_until_opened(self):
        self.assertEqual(self.client.get("/otop/studio/").status_code, 403)
        self._save("OTOP")
        self.host.refresh_from_db()
        self.assertEqual(self.client.get("/otop/studio/").status_code, 200)
        # untouched services stay closed
        self.assertEqual(self.client.get("/services/studio/wellness/").status_code, 403)
        self.assertEqual(self.client.get("/accommodations/studio/").status_code, 200)

    def test_opening_services_shows_menu_and_emails_admin(self):
        self._save("OTOP", "WELLNESS")
        profile = self.host.merchant_profile
        profile.refresh_from_db()
        self.assertEqual(profile.extra_services, ["WELLNESS", "OTOP"])
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [ADMIN_EMAIL])
        self.assertIn("บ้านสวนศรีสะเกษ", mail.outbox[0].subject)
        self.assertIn("เปิดเพิ่ม", mail.outbox[0].body)
        page = self.client.get(reverse("accounts:portal_dashboard")).content.decode()
        self.assertIn("/otop/studio/", page)
        self.assertIn("/services/studio/wellness/", page)
        self.assertNotIn("/services/studio/restaurant/", page)
        self.assertTrue(AuditLog.objects.filter(model_name="MerchantProfile", action="UPDATE").exists())

    def test_saving_without_change_sends_no_email(self):
        self._save("OTOP")
        self._save("OTOP")
        self.assertEqual(len(mail.outbox), 1)

    def test_closing_a_service_emails_admin_again(self):
        self._save("OTOP")
        self._save()
        self.assertEqual(len(mail.outbox), 2)
        self.assertIn("ปิด", mail.outbox[1].body)
        self.assertEqual(self.client.get("/otop/studio/").status_code, 403)

    def test_cannot_close_service_with_products_on_sale(self):
        self._save("OTOP")
        product = OTOPProduct.objects.create(owner=self.host, name="ผ้าไหม", price=Decimal("500"))
        self._save()
        self.host.merchant_profile.refresh_from_db()
        self.assertEqual(self.host.merchant_profile.extra_services, ["OTOP"])
        product.is_active = False
        product.save()
        self._save()
        self.host.merchant_profile.refresh_from_db()
        self.assertEqual(self.host.merchant_profile.extra_services, [])

    def test_main_category_and_bogus_codes_are_ignored(self):
        self._save("HOMESTAY", "ROCKET")
        self.host.merchant_profile.refresh_from_db()
        self.assertEqual(self.host.merchant_profile.extra_services, [])
        self.assertEqual(len(mail.outbox), 0)

    def test_extra_service_needs_approved_shop(self):
        pending = make_partner(email="new@example.com", status=MerchantApprovalStatus.PENDING, extras=["OTOP"])
        self.client.force_login(pending)
        self.assertEqual(self.client.get(reverse("accounts:portal_services")).status_code, 200)
        self.assertEqual(self.client.get("/otop/studio/").status_code, 403)

    def test_tourist_is_turned_away(self):
        tourist = User.objects.create_user(email="t@example.com", password="x", role=UserRoles.TOURIST)
        self.client.force_login(tourist)
        self.assertEqual(self.client.get(reverse("accounts:portal_services")).status_code, 302)
        self.assertEqual(self.client.get(reverse("accounts:portal_payout")).status_code, 302)

    def test_homestay_with_otop_creates_its_own_products(self):
        self._save("OTOP")
        self.client.post("/otop/studio/", {
            "name": "น้ำพริก", "description": "", "price": "80", "stock_quantity": "10",
            "category": OTOPProduct._meta.get_field("category").default,
        })
        self.assertEqual(OTOPProduct.objects.filter(owner=self.host).count(), 1)

    def test_admin_can_set_extras_and_pick_partner_as_owner(self):
        admin = User.objects.create_user(email="admin@example.com", password="x", role=UserRoles.SUPER_ADMIN)
        self.client.force_login(admin)
        self.client.post(reverse("accounts:admin_partner_edit", args=[self.host.id]), {
            "business_name": "บ้านสวนศรีสะเกษ", "business_category": "HOMESTAY",
            "extra_services_present": "1", "extra_services": ["OTOP", "HOMESTAY"],
        })
        self.host.merchant_profile.refresh_from_db()
        self.assertEqual(self.host.merchant_profile.extra_services, ["OTOP"])
        page = self.client.get("/accounts/admin-center/?tab=approvals").content.decode()
        self.assertIn("x-show=\"type === 'OTOP'\">บ้านสวนศรีสะเกษ", page)


@override_settings(ADMIN_EMAIL=ADMIN_EMAIL)
class PayoutAccountTestCase(TestCase):
    VALID = {
        "payout_bank": "KBANK", "payout_account_number": "123-4-56789-0",
        "payout_account_name": "  นาย  ใจดี  มีสุข ", "promptpay_id": "081-234-5678",
    }

    def setUp(self):
        self.host = make_partner()
        self.client.force_login(self.host)

    def test_saves_cleaned_account_and_emails_masked_number(self):
        self.client.post(reverse("accounts:portal_payout"), self.VALID)
        profile = MerchantProfile.objects.get(user=self.host)
        self.assertEqual(profile.payout_account_number, "1234567890")
        self.assertEqual(profile.payout_account_name, "นาย ใจดี มีสุข")
        self.assertEqual(profile.promptpay_id, "0812345678")
        self.assertTrue(profile.has_payout_account)
        self.assertEqual(len(mail.outbox), 1)
        body = mail.outbox[0].body
        self.assertIn("xxxxxx7890", body)
        self.assertNotIn("1234567890", body)
        log = AuditLog.objects.filter(model_name="MerchantProfile").latest("timestamp")
        self.assertNotIn("1234567890", str(log.changes))

    def test_same_details_again_sends_no_email(self):
        self.client.post(reverse("accounts:portal_payout"), self.VALID)
        self.client.post(reverse("accounts:portal_payout"), self.VALID)
        self.assertEqual(len(mail.outbox), 1)

    def test_validation(self):
        bad = [
            {"payout_bank": ""},
            {"payout_bank": "NOTABANK"},
            {"payout_account_number": "12345"},
            {"payout_account_number": "12345abcde"},
            {"payout_account_name": ""},
            {"promptpay_id": "12345"},
            {"promptpay_id": "8812345678"},
        ]
        for change in bad:
            with self.subTest(change=change):
                self.assertFalse(PayoutAccountForm({**self.VALID, **change}, instance=self.host.merchant_profile).is_valid())
        self.assertTrue(PayoutAccountForm({**self.VALID, "promptpay_id": ""}, instance=self.host.merchant_profile).is_valid())
        self.assertTrue(PayoutAccountForm({**self.VALID, "promptpay_id": "1234567890123"}, instance=self.host.merchant_profile).is_valid())

    def test_account_never_on_public_storefront(self):
        self.client.post(reverse("accounts:portal_payout"), self.VALID)
        profile = MerchantProfile.objects.get(user=self.host)
        self.client.logout()
        page = self.client.get(reverse("core:shop_detail", args=[profile.id])).content.decode()
        self.assertNotIn("1234567890", page)
        self.assertNotIn("0812345678", page)

    def test_admin_sees_full_account(self):
        self.client.post(reverse("accounts:portal_payout"), self.VALID)
        admin = User.objects.create_user(email="admin@example.com", password="x", role=UserRoles.SUPER_ADMIN)
        self.client.force_login(admin)
        page = self.client.get("/accounts/admin-center/?tab=approvals").content.decode()
        self.assertIn("1234567890", page)
        self.assertIn("นาย ใจดี มีสุข", page)
