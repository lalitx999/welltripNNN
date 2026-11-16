from django.db import models


class DailyVisitStat(models.Model):
    """
    Site traffic for one day (Asia/Bangkok), for reports to funders.

    Only totals are stored: no IP address, cookie or user is kept. A visitor is
    counted once per day; see apps.core.services.visits.
    """
    date = models.DateField(unique=True)
    visitors = models.PositiveIntegerField(default=0)
    page_views = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "core_daily_visit_stats"
        ordering = ("-date",)

    def __str__(self):
        return f"{self.date}: {self.visitors} visitors, {self.page_views} page views"


class ReportAdjustment(models.Model):
    """
    A figure an admin changed on the report page before exporting it.

    The computed value is kept next to the new one, and every change also goes
    to the audit log, so the original numbers can always be traced back.
    """
    period_start = models.DateField()
    period_end = models.DateField()
    metric = models.CharField(max_length=40)
    original_value = models.DecimalField(max_digits=14, decimal_places=2)
    adjusted_value = models.DecimalField(max_digits=14, decimal_places=2)
    reason = models.CharField(max_length=255)
    changed_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, related_name="report_adjustments",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "core_report_adjustments"
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["period_start", "period_end", "metric"])]

    def __str__(self):
        return f"{self.metric} {self.period_start}..{self.period_end}: {self.original_value} -> {self.adjusted_value}"
