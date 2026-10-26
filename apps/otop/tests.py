from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from apps.accounts.models import User, UserRoles, AuditLog
from apps.otop.models import OTOPProduct, OTOPCategory


class OTOPStudioSecurityTestCase(TestCase):
    """
    Security Test Suite for OTOP Partner Studio:
    Verifies HTMX inline stock editing, Anti-Negative stock guards, and IDOR protection.
    """

    def setUp(self):
        self.client = Client()
        self.password = "StrongPass123!"

        self.otop_owner1 = User.objects.create_user(
            email="otop1@example.com",
            password=self.password,
            role=UserRoles.OTOP_OWNER,
        )
        self.otop_owner2 = User.objects.create_user(
            email="otop2@example.com",
            password=self.password,
            role=UserRoles.OTOP_OWNER,
        )

        self.product = OTOPProduct.objects.create(
            owner=self.otop_owner1,
            name="ผ้าไหมมัดหมี่",
            category=OTOPCategory.TEXTILE,
            price=Decimal("1500.00"),
            stock_quantity=5,
        )

    def test_otop_htmx_stock_increment(self):
        """Owner can increment stock via HTMX and action is logged to AuditLog."""
        self.client.force_login(self.otop_owner1)
        url = reverse('otop:stock_update', kwargs={'product_id': self.product.id})

        response = self.client.post(url, {'delta': 1})
        self.assertEqual(response.status_code, 200)

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 6)

        # Verify AuditLog logged the stock update
        log = AuditLog.objects.filter(action="UPDATE", model_name="OTOPProduct", object_id=str(self.product.id)).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.changes['stock_quantity'], {'from': 5, 'to': 6})

    def test_otop_htmx_stock_anti_negative_guard(self):
        """
        WHY: Inventory must never drop below 0.
        Decrementing below zero must be rejected with HTTP 400.
        """
        self.client.force_login(self.otop_owner1)
        url = reverse('otop:stock_update', kwargs={'product_id': self.product.id})

        # Product stock is 5, attempting delta = -10 must fail
        response = self.client.post(url, {'delta': -10})
        self.assertEqual(response.status_code, 400)

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 5)

    def test_otop_stock_update_idor_blocked(self):
        """
        WHY: Owner 2 must never be able to adjust Owner 1's product stock.
        """
        self.client.force_login(self.otop_owner2)
        url = reverse('otop:stock_update', kwargs={'product_id': self.product.id})

        # Owner 2 gets HTTP 404 (Anti-IDOR)
        response = self.client.post(url, {'delta': 1})
        self.assertEqual(response.status_code, 404)

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 5)
