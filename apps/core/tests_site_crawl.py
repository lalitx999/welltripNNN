"""
Site-wide smoke crawl (pre-launch QC): every role opens every page it can reach by following
links from its home pages. Any 500, broken internal link or missing static file fails the test.
"""
import re
from datetime import date, time, timedelta
from decimal import Decimal
from urllib.parse import urldefrag, urlparse

from django.contrib.staticfiles import finders
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accommodations.models import Accommodation, AccommodationStatus, Room
from apps.accounts.models import MerchantApprovalStatus, MerchantProfile, User, UserRoles
from apps.bookings.models import Booking, BookingItem, BookingStatus
from apps.community.models import Coupon, Event, MapLocation
from apps.otop.models import OTOPProduct
from apps.payments.models import Payment
from apps.services.models import FoodMenu, WellnessService, WellnessTimeSlot

HREF = re.compile(r'''(?:href|src)="([^"#][^"]*)"''')
SKIP = ("/accounts/logout", "/accounts/google/", "/i18n/", "/media/", "mailto:", "tel:", "javascript:")
MAX_PAGES = 250


def _merchant(role, email):
    user = User.objects.create_user(email=email, password="x", role=role, first_name="ร้าน", email_verified=True)
    MerchantProfile.objects.create(user=user, business_name=email, status=MerchantApprovalStatus.APPROVED)
    return user


@override_settings(EASYSLIP_API_KEY="")
class SiteCrawlTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.host = _merchant(UserRoles.HOMESTAY_OWNER, "host@example.com")
        cls.cook = _merchant(UserRoles.RESTAURANT_OWNER, "cook@example.com")
        cls.spa = _merchant(UserRoles.WELLNESS_OWNER, "spa@example.com")
        cls.seller = _merchant(UserRoles.OTOP_OWNER, "seller@example.com")
        cls.tourist = User.objects.create_user(email="t@example.com", password="x", role=UserRoles.TOURIST,
                                               first_name="ลลิตา", email_verified=True)
        cls.admin = User.objects.create_user(email="admin@example.com", password="x", role=UserRoles.COMMUNITY_ADMIN,
                                             email_verified=True)
        cls.root = User.objects.create_user(email="root@example.com", password="x", role=UserRoles.SUPER_ADMIN,
                                            email_verified=True)

        acc = Accommodation.objects.create(owner=cls.host, name="บ้านสวนริมนา", district="กันทรลักษ์",
                                           status=AccommodationStatus.ACTIVE)
        Room.objects.create(accommodation=acc, name="ห้องริมนา", base_price_per_night=Decimal("800"))
        food = FoodMenu.objects.create(owner=cls.cook, name="ส้มตำสมุนไพร", price=Decimal("80"))
        spa = WellnessService.objects.create(owner=cls.spa, name="นวดประคบ", price=Decimal("300"), duration_minutes=60)
        WellnessTimeSlot.objects.create(service=spa, date=date.today() + timedelta(days=3), start_time=time(10),
                                        end_time=time(11), capacity_total=3, capacity_available=3)
        product = OTOPProduct.objects.create(owner=cls.seller, name="กาแฟภูเขาไฟ", price=Decimal("250"), stock_quantity=5)
        MapLocation.objects.create(title="ผามออีแดง", latitude=14.4, longitude=104.6)
        Event.objects.create(title="งานดอกลำดวน", start_date=date.today() + timedelta(days=10),
                             end_date=date.today() + timedelta(days=12))
        Coupon.objects.create(code="WELCOME50", discount_amount=Decimal("50"),
                              expires_at=timezone.now() + timedelta(days=30))

        for status in (BookingStatus.CONFIRMED, BookingStatus.AWAITING_PAYMENT):
            booking = Booking.objects.create(customer=cls.tourist, total_amount=Decimal("1130"), status=status)
            for vendor, kind, entity, title, price in (
                (cls.host, "ROOM", acc.id, "ห้องริมนา", "800"),
                (cls.cook, "FOOD", food.id, "ส้มตำสมุนไพร", "80"),
                (cls.seller, "OTOP", product.id, "กาแฟภูเขาไฟ", "250"),
            ):
                BookingItem.objects.create(booking=booking, vendor=vendor, item_type=kind, entity_id=str(entity),
                                           item_title_snapshot=title, unit_price_snapshot=Decimal(price),
                                           subtotal=Decimal(price))
            Payment.objects.create(booking=booking, amount=booking.total_amount)

    def _crawl(self, user, starts):
        if user:
            self.client.force_login(user)
        else:
            self.client.logout()
        seen, queue, problems = set(), list(starts), []
        while queue and len(seen) < MAX_PAGES:
            url = queue.pop(0)
            if url in seen:
                continue
            seen.add(url)
            if url.startswith("/static/"):
                if not finders.find(url[len("/static/"):].split("?")[0]):
                    problems.append(f"missing static {url}")
                continue
            try:
                response = self.client.get(url)
            except Exception as exc:  # template or view crash
                problems.append(f"CRASH {url}: {exc.__class__.__name__}: {exc}")
                continue
            if response.status_code >= 500:
                problems.append(f"{response.status_code} {url}")
            elif response.status_code == 404:
                problems.append(f"404 {url}")
            if response.status_code != 200 or "text/html" not in response.get("Content-Type", ""):
                continue
            for href in HREF.findall(response.content.decode("utf-8", "ignore")):
                href = urldefrag(href.replace("&amp;", "&"))[0]
                parsed = urlparse(href)
                if parsed.scheme or parsed.netloc or not href.startswith("/") or href.startswith(SKIP):
                    continue
                # Calendars link month after month forever: visit each path at most 3 times
                if href not in seen and sum(1 for u in seen if urlparse(u).path == parsed.path) < 3:
                    queue.append(href)
        return problems, len(seen)

    def test_every_role_crawl(self):
        roles = {
            "anonymous": (None, ["/", "/home/", "/accounts/login/", "/accounts/register/"]),
            "tourist": (self.tourist, ["/home/", "/bookings/my-bookings/", "/bookings/cart/", "/accounts/profile/"]),
            "homestay": (self.host, ["/accounts/portal/"]),
            "restaurant": (self.cook, ["/accounts/portal/"]),
            "wellness": (self.spa, ["/accounts/portal/"]),
            "otop": (self.seller, ["/accounts/portal/"]),
            "community_admin": (self.admin, ["/accounts/admin-center/", "/accounts/portal/"]),
            "super_admin": (self.root, ["/accounts/admin-center/"]),
        }
        report = []
        for name, (user, starts) in roles.items():
            problems, count = self._crawl(user, starts)
            report.append(f"[{name}] {count} urls")
            report += [f"   {p}" for p in problems]
        self.assertFalse([line for line in report if line.startswith("   ")], "\n".join(report))
