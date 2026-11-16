import csv
import io
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook

from apps.accounts.models import AuditLog, User, UserRoles
from apps.bookings.models import BookingStatus
from apps.bookings.services.checkout import process_checkout
from apps.core.models import DailyVisitStat, ReportAdjustment
from apps.core.services.reports import build_report
from apps.otop.models import OTOPProduct


class ReportTests(TestCase):
    def setUp(self):
        self.today = timezone.localdate()
        self.admin = User.objects.create_user(email="rep_admin@example.com", password="x", role=UserRoles.COMMUNITY_ADMIN)
        self.tourist = User.objects.create_user(email="rep_t@example.com", password="x", role=UserRoles.TOURIST)
        owner = User.objects.create_user(email="rep_o@example.com", password="x", role=UserRoles.OTOP_OWNER)
        product = OTOPProduct.objects.create(owner=owner, name="ผ้าไหมลายลูกแก้ว", price=Decimal("100"), stock_quantity=10)
        paid = process_checkout(self.tourist, [{"item_type": "OTOP", "entity_id": str(product.id), "quantity": 2}])
        paid.status = BookingStatus.CONFIRMED
        paid.save()
        process_checkout(self.tourist, [{"item_type": "OTOP", "entity_id": str(product.id), "quantity": 1}])  # unpaid
        DailyVisitStat.objects.create(date=self.today, visitors=40, page_views=120)
        DailyVisitStat.objects.create(date=self.today - timedelta(days=1), visitors=10, page_views=30)
        self.url = reverse("accounts:admin_reports")
        self.period = {"start": (self.today - timedelta(days=1)).isoformat(), "end": self.today.isoformat()}

    def metrics(self):
        return {m.key: m for m in build_report(self.today - timedelta(days=1), self.today)}

    def test_figures_count_visits_and_paid_orders_only(self):
        m = self.metrics()
        self.assertEqual(m["visitors"].value, 50)
        self.assertEqual(m["page_views"].value, 150)
        self.assertEqual(m["customers"].value, 1)
        self.assertEqual(m["orders"].value, 1)
        self.assertEqual(m["transaction_value"].value, Decimal("210.00"))
        self.assertEqual(m["value_OTOP"].value, Decimal("210.00"))
        self.assertEqual(m["community_income"].value, Decimal("200.00"))
        self.assertEqual(m["platform_fee"].value, Decimal("10.00"))

    def test_admin_edits_a_figure_and_the_change_is_logged(self):
        self.client.force_login(self.admin)
        self.client.post(self.url, {**self.period, "metric": "visitors", "value": "75", "reason": "รวมผู้เข้าชมบูธงาน"})
        m = self.metrics()
        self.assertEqual(m["visitors"].value, Decimal("75"))
        self.assertEqual(m["visitors"].computed, Decimal("50"))
        self.assertTrue(m["visitors"].adjusted)
        adj = ReportAdjustment.objects.get()
        self.assertEqual((adj.original_value, adj.adjusted_value, adj.changed_by), (Decimal("50"), Decimal("75"), self.admin))
        log = AuditLog.objects.filter(model_name="Report", action="UPDATE").get()
        self.assertEqual(log.changes["from"], "50")
        self.assertEqual(log.changes["to"], "75")
        page = self.client.get(self.url, self.period)
        self.assertContains(page, "รวมผู้เข้าชมบูธงาน")

    def test_an_edit_needs_a_reason(self):
        self.client.force_login(self.admin)
        self.client.post(self.url, {**self.period, "metric": "visitors", "value": "75", "reason": ""})
        self.assertFalse(ReportAdjustment.objects.exists())

    def test_reset_returns_to_the_computed_figure_and_keeps_history(self):
        self.client.force_login(self.admin)
        self.client.post(self.url, {**self.period, "metric": "orders", "value": "9", "reason": "ทดสอบ"})
        self.client.post(self.url, {**self.period, "metric": "orders", "action": "reset"})
        self.assertEqual(self.metrics()["orders"].value, 1)
        self.assertEqual(ReportAdjustment.objects.count(), 2)

    def test_exports_use_the_edited_figures(self):
        self.client.force_login(self.admin)
        self.client.post(self.url, {**self.period, "metric": "visitors", "value": "75", "reason": "รวมบูธ"})
        xlsx = self.client.get(self.url, {**self.period, "export": "xlsx"})
        self.assertEqual(xlsx["Content-Type"], "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        wb = load_workbook(io.BytesIO(xlsx.content))
        summary = {row[0]: row[1] for row in wb.worksheets[0].iter_rows(values_only=True) if row and row[0]}
        self.assertEqual(summary["ผู้เข้าชมเว็บไซต์ (คนไม่ซ้ำต่อวัน)"], 75)
        self.assertEqual(len(wb.sheetnames), 3)

        pdf = self.client.get(self.url, {**self.period, "export": "pdf"})
        self.assertEqual(pdf["Content-Type"], "application/pdf")
        self.assertTrue(pdf.content.startswith(b"%PDF"))

        sales = self.client.get(self.url, {**self.period, "export": "csv_sales"})
        rows = list(csv.reader(io.StringIO(sales.content.decode("utf-8-sig"))))
        self.assertEqual(len(rows), 2)  # header + the one paid line
        self.assertIn("ผ้าไหมลายลูกแก้ว", rows[1])

        visits = self.client.get(self.url, {**self.period, "export": "csv_visits"})
        self.assertEqual(len(list(csv.reader(io.StringIO(visits.content.decode("utf-8-sig"))))), 3)
        self.assertEqual(AuditLog.objects.filter(action="EXPORT").count(), 4)

    def test_only_admins_see_reports(self):
        self.client.force_login(self.tourist)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.client.post(self.url, {**self.period, "metric": "visitors", "value": "1", "reason": "x"})
        self.assertFalse(ReportAdjustment.objects.exists())
