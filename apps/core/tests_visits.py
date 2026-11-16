from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User, UserRoles
from apps.core.models import DailyVisitStat

BROWSER = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
PHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1"


class VisitCounterTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client(HTTP_USER_AGENT=BROWSER)

    def stat(self):
        return DailyVisitStat.objects.filter(date=timezone.localdate()).first()

    def test_same_visitor_is_counted_once_a_day_but_every_page_view_counts(self):
        self.client.get("/")
        self.client.get("/")
        self.client.get(reverse("accommodations:list"))
        self.assertEqual(self.stat().visitors, 1)
        self.assertEqual(self.stat().page_views, 3)

    def test_different_browsers_are_different_visitors(self):
        self.client.get("/")
        Client(HTTP_USER_AGENT=PHONE).get("/")
        Client(HTTP_USER_AGENT=BROWSER, REMOTE_ADDR="10.0.0.9").get("/")
        self.assertEqual(self.stat().visitors, 3)

    def test_bots_and_missing_user_agents_are_not_counted(self):
        Client(HTTP_USER_AGENT="Googlebot/2.1 (+http://www.google.com/bot.html)").get("/")
        Client(HTTP_USER_AGENT="curl/8.5.0").get("/")
        Client().get("/")
        self.assertIsNone(self.stat())

    def test_files_errors_and_non_page_requests_are_not_counted(self):
        self.client.get("/robots.txt")
        self.client.get("/this-page-does-not-exist/")
        self.client.post("/")
        self.client.get("/", HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertIsNone(self.stat())

    def test_service_worker_preloads_are_not_counted(self):
        self.client.get("/offline/", HTTP_SEC_FETCH_MODE="navigate")
        self.client.get("/", HTTP_SEC_FETCH_MODE="cors")
        self.assertIsNone(self.stat())
        self.client.get("/", HTTP_SEC_FETCH_MODE="navigate")
        self.assertEqual(self.stat().page_views, 1)

    def test_admins_are_not_counted(self):
        admin = User.objects.create_user(email="visits_admin@example.com", password="x", role=UserRoles.COMMUNITY_ADMIN)
        self.client.force_login(admin)
        self.client.get("/")
        self.assertIsNone(self.stat())

    def test_no_personal_data_is_stored(self):
        self.client.get("/")
        fields = {f.name for f in DailyVisitStat._meta.get_fields()}
        self.assertEqual(fields, {"id", "date", "visitors", "page_views"})

    def test_admin_dashboard_shows_the_counts(self):
        self.client.get("/")
        Client(HTTP_USER_AGENT=PHONE).get("/")
        admin = User.objects.create_user(email="visits_admin2@example.com", password="x", role=UserRoles.COMMUNITY_ADMIN)
        self.client.force_login(admin)
        response = self.client.get(reverse("accounts:admin_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["visits"]["today"], {"visitors": 2, "page_views": 2})
        self.assertEqual(len(response.context["visits"]["series"]), 14)
        self.assertContains(response, "ผู้เข้าชมเว็บไซต์")
