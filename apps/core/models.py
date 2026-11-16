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
