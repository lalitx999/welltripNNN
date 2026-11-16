"""
Admin reports for funders: site visitors, customers served, spending and
transaction value over a date range, exported as Excel, PDF or raw CSV.

Figures are computed from the database. An admin may change a figure before
exporting (ReportAdjustment); the export then uses the changed value, while the
computed value stays stored next to it and the change is audit-logged.

Sales count orders that were paid: CONFIRMED (incl. deposit bookings whose
deposit was confirmed) and COMPLETED, by order date (Asia/Bangkok).
"""
import csv
import io
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path

from django.db.models import Count, Sum
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from apps.core.models import DailyVisitStat, ReportAdjustment

FONT_DIR = Path(__file__).resolve().parent.parent / "fonts"


@dataclass
class Metric:
    key: str
    label: str
    unit: str  # "people", "times", "baht"
    computed: Decimal
    value: Decimal  # computed, or the latest admin adjustment
    adjusted: bool = False
    group: str = ""

    @property
    def display(self):
        if self.unit == "baht":
            return f"฿{self.value:,.2f}"
        return f"{self.value:,.0f}"


METRICS = [
    # key, label, unit, group
    ("visitors", gettext_lazy("ผู้เข้าชมเว็บไซต์ (คนไม่ซ้ำต่อวัน)"), "people", gettext_lazy("การเข้าชม")),
    ("page_views", gettext_lazy("จำนวนหน้าที่เปิดชม"), "times", gettext_lazy("การเข้าชม")),
    ("customers", gettext_lazy("ผู้เข้าใช้บริการ (ลูกค้าที่ชำระเงิน)"), "people", gettext_lazy("การใช้บริการ")),
    ("orders", gettext_lazy("จำนวนคำสั่งซื้อ/การจองที่ชำระแล้ว"), "times", gettext_lazy("การใช้บริการ")),
    ("guests", gettext_lazy("จำนวนผู้เข้าพัก (คน-คืน)"), "people", gettext_lazy("การใช้บริการ")),
    ("transaction_value", gettext_lazy("มูลค่าการซื้อขายรวม"), "baht", gettext_lazy("มูลค่าการซื้อขาย")),
    ("value_ROOM", gettext_lazy("ที่พัก / โฮมสเตย์"), "baht", gettext_lazy("มูลค่าการซื้อขาย")),
    ("value_WELLNESS", gettext_lazy("นวดแผนไทย / สปา"), "baht", gettext_lazy("มูลค่าการซื้อขาย")),
    ("value_FOOD", gettext_lazy("อาหารสุขภาพ"), "baht", gettext_lazy("มูลค่าการซื้อขาย")),
    ("value_OTOP", gettext_lazy("สินค้าชุมชน OTOP"), "baht", gettext_lazy("มูลค่าการซื้อขาย")),
    ("spend_per_customer", gettext_lazy("ยอดใช้จ่ายเฉลี่ยต่อผู้ใช้บริการ"), "baht", gettext_lazy("ยอดค่าใช้จ่าย")),
    ("community_income", gettext_lazy("รายได้เข้าชุมชน (ผู้ประกอบการได้รับ)"), "baht", gettext_lazy("ยอดค่าใช้จ่าย")),
    ("platform_fee", gettext_lazy("ค่าบริการแพลตฟอร์ม 5%"), "baht", gettext_lazy("ยอดค่าใช้จ่าย")),
    ("balance_outstanding", gettext_lazy("ยอดค้างชำระหน้างาน (มัดจำ)"), "baht", gettext_lazy("ยอดค่าใช้จ่าย")),
]
METRIC_KEYS = [m[0] for m in METRICS]


def default_period():
    today = timezone.localdate()
    return today.replace(day=1), today


def parse_period(start, end):
    """Dates from the query string, falling back to this month; start <= end, at most 3 years."""
    def parse(value):
        try:
            return datetime.strptime(str(value), "%Y-%m-%d").date()
        except (TypeError, ValueError):
            return None
    d_start, d_end = default_period()
    start, end = parse(start) or d_start, parse(end) or d_end
    if end < start:
        start, end = end, start
    return max(start, end - timedelta(days=366 * 3)), end


def _paid_bookings(start, end):
    from apps.bookings.models import Booking, BookingStatus
    tz = timezone.get_current_timezone()
    since = timezone.make_aware(datetime.combine(start, time.min), tz)
    until = timezone.make_aware(datetime.combine(end + timedelta(days=1), time.min), tz)
    return Booking.objects.filter(
        status__in=[BookingStatus.CONFIRMED, BookingStatus.COMPLETED], created_at__gte=since, created_at__lt=until,
    )


def compute(start: date, end: date) -> dict:
    from apps.bookings.models import BookingItem, BookingItemType

    visits = DailyVisitStat.objects.filter(date__gte=start, date__lte=end).aggregate(v=Sum("visitors"), p=Sum("page_views"))
    bookings = _paid_bookings(start, end)
    items = BookingItem.objects.filter(booking__in=bookings)
    totals = bookings.aggregate(total=Sum("total_amount"), orders=Count("id"), customers=Count("customer", distinct=True))
    by_type = dict(items.values_list("item_type").annotate(s=Sum("subtotal")).values_list("item_type", "s"))
    split = items.aggregate(owner=Sum("owner_amount"), fee=Sum("platform_fee"))
    outstanding = bookings.filter(payment_plan="DEPOSIT", balance_paid_at__isnull=True).aggregate(s=Sum("balance_due"))["s"]

    guests = 0
    for item in items.filter(item_type=BookingItemType.ROOM).only("quantity", "booking_metadata"):
        guests += int(item.booking_metadata.get("guests") or 1) * item.quantity

    value = totals["total"] or Decimal("0")
    customers = totals["customers"] or 0
    return {
        "visitors": Decimal(visits["v"] or 0),
        "page_views": Decimal(visits["p"] or 0),
        "customers": Decimal(customers),
        "orders": Decimal(totals["orders"] or 0),
        "guests": Decimal(guests),
        "transaction_value": value,
        "value_ROOM": by_type.get("ROOM") or Decimal("0"),
        "value_WELLNESS": by_type.get("WELLNESS") or Decimal("0"),
        "value_FOOD": by_type.get("FOOD") or Decimal("0"),
        "value_OTOP": by_type.get("OTOP") or Decimal("0"),
        "spend_per_customer": (value / customers).quantize(Decimal("0.01")) if customers else Decimal("0"),
        "community_income": split["owner"] or Decimal("0"),
        "platform_fee": split["fee"] or Decimal("0"),
        "balance_outstanding": outstanding or Decimal("0"),
    }


def latest_adjustments(start, end):
    found = {}
    for adj in ReportAdjustment.objects.filter(period_start=start, period_end=end).order_by("created_at"):
        found[adj.metric] = adj  # later ones win
    return found


def build_report(start: date, end: date) -> list:
    computed = compute(start, end)
    adjustments = latest_adjustments(start, end)
    metrics = []
    for key, label, unit, group in METRICS:
        adj = adjustments.get(key)
        metrics.append(Metric(
            key=key, label=str(label), unit=unit, group=str(group), computed=computed[key],
            value=adj.adjusted_value if adj else computed[key], adjusted=adj is not None,
        ))
    return metrics


def adjust_metric(request, start, end, key, new_value, reason):
    """Store an admin's change to one figure and audit-log it. Returns (ok, message)."""
    from apps.accounts.services.audit import record_audit_log

    if key not in METRIC_KEYS:
        return False, _("ไม่พบตัวชี้วัดนี้")
    reason = (reason or "").strip()
    if not reason:
        return False, _("กรุณาระบุเหตุผลที่แก้ตัวเลข")
    try:
        value = Decimal(str(new_value).replace(",", "").replace("฿", "").strip())
    except Exception:
        return False, _("ตัวเลขไม่ถูกต้อง")
    if value < 0 or value > Decimal("999999999999"):
        return False, _("ตัวเลขไม่ถูกต้อง")
    computed = compute(start, end)[key]
    previous = latest_adjustments(start, end).get(key)
    adj = ReportAdjustment.objects.create(
        period_start=start, period_end=end, metric=key, original_value=computed,
        adjusted_value=value, reason=reason[:255], changed_by=request.user,
    )
    record_audit_log(
        request=request, action="UPDATE", model_name="Report", object_id=f"{start}..{end}",
        changes={
            "metric": key, "computed": str(computed),
            "from": str(previous.adjusted_value if previous else computed), "to": str(value), "reason": adj.reason,
        },
        user=request.user,
    )
    return True, _("แก้ตัวเลขแล้ว ระบบบันทึกค่าเดิมและผู้แก้ไว้ในประวัติ")


def reset_metric(request, start, end, key):
    """Go back to the computed figure (adjustment history is kept)."""
    from apps.accounts.services.audit import record_audit_log

    previous = latest_adjustments(start, end).get(key)
    if not previous:
        return False, _("ตัวเลขนี้ยังไม่ถูกแก้")
    computed = compute(start, end)[key]
    ReportAdjustment.objects.create(
        period_start=start, period_end=end, metric=key, original_value=computed,
        adjusted_value=computed, reason=_("กลับไปใช้ค่าที่ระบบคำนวณ"), changed_by=request.user,
    )
    record_audit_log(
        request=request, action="UPDATE", model_name="Report", object_id=f"{start}..{end}",
        changes={"metric": key, "from": str(previous.adjusted_value), "to": str(computed), "reason": "reset"},
        user=request.user,
    )
    return True, _("กลับไปใช้ตัวเลขที่ระบบคำนวณแล้ว")


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------

def _title(start, end):
    return _("รายงานสรุป WellTrip Sisaket {start} ถึง {end}").format(
        start=start.strftime("%d/%m/%Y"), end=end.strftime("%d/%m/%Y"),
    )


def daily_visits(start, end):
    stats = {s.date: s for s in DailyVisitStat.objects.filter(date__gte=start, date__lte=end)}
    day = start
    while day <= end:
        stat = stats.get(day)
        yield day, (stat.visitors if stat else 0), (stat.page_views if stat else 0)
        day += timedelta(days=1)


def sales_lines(start, end):
    from apps.bookings.models import BookingItem
    return (
        BookingItem.objects.filter(booking__in=_paid_bookings(start, end))
        .select_related("booking", "vendor")
        .order_by("booking__created_at", "id")
    )


SALES_HEADER = [
    gettext_lazy("รหัสคำสั่งซื้อ"), gettext_lazy("วันที่สั่ง"), gettext_lazy("สถานะ"), gettext_lazy("วิธีชำระ"),
    gettext_lazy("ประเภท"), gettext_lazy("รายการ"), gettext_lazy("วันที่ใช้บริการ"), gettext_lazy("จำนวน"),
    gettext_lazy("ยอดลูกค้าจ่าย"), gettext_lazy("ผู้ประกอบการได้รับ"), gettext_lazy("ค่าบริการแพลตฟอร์ม"),
    gettext_lazy("ผู้ประกอบการ"),
]


def _sales_row(item):
    booking = item.booking
    return [
        booking.booking_code,
        timezone.localtime(booking.created_at).strftime("%Y-%m-%d %H:%M"),
        str(booking.get_status_display()),
        str(booking.get_payment_plan_display()),
        str(item.get_item_type_display()),
        item.item_title_snapshot,
        item.booking_metadata.get("date", ""),
        item.quantity,
        item.subtotal,
        item.owner_amount,
        item.platform_fee,
        str(getattr(item.vendor, "display_name", "") or item.vendor.email),
    ]


def export_csv(start, end, kind):
    """Raw data as UTF-8 CSV (with BOM so Excel shows Thai correctly)."""
    buffer = io.StringIO()
    buffer.write("﻿")
    writer = csv.writer(buffer)
    if kind == "visits":
        writer.writerow([_("วันที่"), _("ผู้เข้าชม"), _("จำนวนหน้าที่เปิด")])
        for day, visitors, views in daily_visits(start, end):
            writer.writerow([day.isoformat(), visitors, views])
    else:
        writer.writerow([str(h) for h in SALES_HEADER])
        for item in sales_lines(start, end):
            writer.writerow(_sales_row(item))
    return buffer.getvalue().encode("utf-8")


def export_xlsx(start, end, metrics):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = _("สรุป")
    bold = Font(bold=True)
    green = PatternFill("solid", fgColor="E3F6EC")
    ws.append([_title(start, end)])
    ws["A1"].font = Font(bold=True, size=14)
    ws.append([_("จัดทำเมื่อ {when}").format(when=timezone.localtime().strftime("%d/%m/%Y %H:%M"))])
    ws.append([])
    group = None
    for m in metrics:
        if m.group != group:
            group = m.group
            ws.append([group])
            ws.cell(ws.max_row, 1).font = bold
            ws.cell(ws.max_row, 1).fill = green
        ws.append([m.label, float(m.value)])
        cell = ws.cell(ws.max_row, 2)
        cell.number_format = "#,##0.00" if m.unit == "baht" else "#,##0"
        cell.alignment = Alignment(horizontal="right")
    ws.column_dimensions["A"].width = 46
    ws.column_dimensions["B"].width = 18

    daily = wb.create_sheet(_("ผู้เข้าชมรายวัน"))
    daily.append([_("วันที่"), _("ผู้เข้าชม"), _("จำนวนหน้าที่เปิด")])
    for c in daily[1]:
        c.font = bold
    for day, visitors, views in daily_visits(start, end):
        daily.append([day, visitors, views])
        daily.cell(daily.max_row, 1).number_format = "yyyy-mm-dd"
    daily.column_dimensions["A"].width = 14

    sales = wb.create_sheet(_("รายการขาย"))
    sales.append([str(h) for h in SALES_HEADER])
    for c in sales[1]:
        c.font = bold
    for item in sales_lines(start, end):
        row = _sales_row(item)
        sales.append([float(v) if isinstance(v, Decimal) else v for v in row])
    for col, width in zip("ABCDEFGHIJKL", (16, 17, 16, 22, 18, 40, 13, 8, 14, 16, 16, 26)):
        sales.column_dimensions[col].width = width

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def export_pdf(start, end, metrics):
    from fpdf import FPDF
    from fpdf.enums import XPos, YPos

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_margins(18, 18, 18)
    pdf.add_font("NotoThai", "", str(FONT_DIR / "NotoSansThai-Regular.ttf"))
    pdf.add_font("NotoThai", "B", str(FONT_DIR / "NotoSansThai-Bold.ttf"))
    pdf.add_font("NotoLatin", "", str(FONT_DIR / "NotoSans-Regular.ttf"))
    pdf.add_font("NotoLatin", "B", str(FONT_DIR / "NotoSans-Bold.ttf"))
    pdf.set_fallback_fonts(["NotoLatin"])
    pdf.set_text_shaping(True)
    pdf.add_page()

    pdf.set_font("NotoThai", "B", 15)
    pdf.multi_cell(0, 9, _title(start, end), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("NotoThai", "", 9)
    pdf.set_text_color(110, 110, 110)
    pdf.cell(0, 6, _("จัดทำเมื่อ {when}").format(when=timezone.localtime().strftime("%d/%m/%Y %H:%M")), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(3)

    width = pdf.w - pdf.l_margin - pdf.r_margin
    group = None
    for m in metrics:
        if m.group != group:
            group = m.group
            pdf.ln(2)
            pdf.set_fill_color(227, 246, 236)
            pdf.set_font("NotoThai", "B", 11)
            pdf.cell(width, 8, group, fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font("NotoThai", "", 10.5)
        pdf.cell(width * 0.68, 7.5, m.label, border="B")
        pdf.set_font("NotoThai", "B", 10.5)
        pdf.cell(width * 0.32, 7.5, m.display, border="B", align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.ln(6)
    pdf.set_font("NotoThai", "", 8.5)
    pdf.set_text_color(110, 110, 110)
    pdf.multi_cell(0, 5, _(
        "ผู้เข้าชมนับคนไม่ซ้ำวันละครั้ง ไม่รวมบอทและผู้ดูแลระบบ · มูลค่าการซื้อขายนับคำสั่งซื้อที่ชำระเงินแล้ว (รวมการจองที่ชำระมัดจำแล้ว) ตามวันที่สั่ง"
    ))
    return bytes(pdf.output())
