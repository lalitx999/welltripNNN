import datetime
from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from apps.accounts.models import User, UserRoles
from apps.services.models import FoodMenu, WellnessService, WellnessTimeSlot, FoodWellnessCategory


class ServicesStudioSecurityTestCase(TestCase):
    """
    Security Test Suite for Restaurant & Wellness Partner Studios:
    Verifies IDOR defenses and role boundaries.
    """

    def setUp(self):
        self.client = Client()
        self.password = "SecurePassword123!"

        self.restaurant_owner1 = User.objects.create_user(
            email="rest1@example.com",
            password=self.password,
            role=UserRoles.RESTAURANT_OWNER,
        )
        self.restaurant_owner2 = User.objects.create_user(
            email="rest2@example.com",
            password=self.password,
            role=UserRoles.RESTAURANT_OWNER,
        )
        self.wellness_owner1 = User.objects.create_user(
            email="wellness1@example.com",
            password=self.password,
            role=UserRoles.WELLNESS_OWNER,
        )
        self.wellness_owner2 = User.objects.create_user(
            email="wellness2@example.com",
            password=self.password,
            role=UserRoles.WELLNESS_OWNER,
        )

        self.menu_item = FoodMenu.objects.create(
            owner=self.restaurant_owner1,
            name="ข้าวยำเบญจรงค์",
            price=Decimal("120.00"),
            wellness_category=FoodWellnessCategory.ORGANIC,
        )

        self.spa_service = WellnessService.objects.create(
            owner=self.wellness_owner1,
            name="นวดประคบสมุนไพร",
            price=Decimal("600.00"),
        )
        self.spa_slot = WellnessTimeSlot.objects.create(
            service=self.spa_service,
            date=datetime.date(2026, 12, 10),
            start_time=datetime.time(10, 0),
            end_time=datetime.time(11, 0),
            capacity_total=2,
            capacity_available=2,
        )

    def test_restaurant_food_delete_idor_blocked(self):
        """Restaurant Owner 2 cannot delete Restaurant Owner 1's food menu."""
        self.client.force_login(self.restaurant_owner2)
        url = reverse('services:food_delete', kwargs={'food_id': self.menu_item.id})

        # Must return 404 Not Found (Row-level protection)
        response = self.client.post(url)
        self.assertEqual(response.status_code, 404)
        self.assertTrue(FoodMenu.objects.filter(id=self.menu_item.id).exists())

    def test_restaurant_food_delete_owner_allowed(self):
        """Owner 1 can delete their own menu."""
        self.client.force_login(self.restaurant_owner1)
        url = reverse('services:food_delete', kwargs={'food_id': self.menu_item.id})

        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(FoodMenu.objects.filter(id=self.menu_item.id).exists())

    def test_wellness_slot_delete_idor_blocked(self):
        """Wellness Owner 2 cannot delete Wellness Owner 1's time slot."""
        self.client.force_login(self.wellness_owner2)
        url = reverse('services:wellness_slot_delete', kwargs={'slot_id': self.spa_slot.id})

        # Must return 404 Not Found
        response = self.client.post(url)
        self.assertEqual(response.status_code, 404)
        self.assertTrue(WellnessTimeSlot.objects.filter(id=self.spa_slot.id).exists())
