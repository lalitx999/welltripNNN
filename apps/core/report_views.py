"""Admin Center: report page with editable figures and Excel / PDF / CSV exports."""
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils.http import urlencode
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

from apps.accounts.models import UserRoles
from apps.accounts.permissions import role_required
from apps.accounts.services.audit import record_audit_log
from apps.core.models import ReportAdjustment
from apps.core.services import reports

ADMIN_ROLES = (UserRoles.COMMUNITY_ADMIN, UserRoles.SUPER_ADMIN)
EXPORTS = {
    "xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xlsx"),
    "pdf": ("application/pdf", "pdf"),
    "csv_sales": ("text/csv; charset=utf-8", "csv"),
    "csv_visits": ("text/csv; charset=utf-8", "csv"),
}


@role_required(*ADMIN_ROLES)
@require_http_methods(["GET", "POST"])
def report_view(request):
    source = request.POST if request.method == "POST" else request.GET
    start, end = reports.parse_period(source.get("start"), source.get("end"))
    period_query = urlencode({"start": start.isoformat(), "end": end.isoformat()})

    if request.method == "POST":
        key = request.POST.get("metric", "")
        if request.POST.get("action") == "reset":
            ok, message = reports.reset_metric(request, start, end, key)
        else:
            ok, message = reports.adjust_metric(request, start, end, key, request.POST.get("value", ""), request.POST.get("reason", ""))
        (messages.success if ok else messages.error)(request, message)
        return redirect(f"{request.path}?{period_query}")

    export = request.GET.get("export", "")
    if export in EXPORTS:
        metrics = reports.build_report(start, end)
        if export == "xlsx":
            body = reports.export_xlsx(start, end, metrics)
        elif export == "pdf":
            body = reports.export_pdf(start, end, metrics)
        else:
            body = reports.export_csv(start, end, "visits" if export == "csv_visits" else "sales")
        content_type, ext = EXPORTS[export]
        name = f"welltrip-report-{start:%Y%m%d}-{end:%Y%m%d}{'-' + export.split('_')[1] if '_' in export else ''}.{ext}"
        record_audit_log(
            request=request, action="EXPORT", model_name="Report", object_id=f"{start}..{end}",
            changes={"format": export}, user=request.user,
        )
        response = HttpResponse(body, content_type=content_type)
        response["Content-Disposition"] = f'attachment; filename="{name}"'
        return response

    metrics = reports.build_report(start, end)
    return render(request, "admin/reports.html", {
        "active_tab": "reports",
        "start": start,
        "end": end,
        "period_query": period_query,
        "metrics": metrics,
        "history": ReportAdjustment.objects.filter(period_start=start, period_end=end).select_related("changed_by")[:50],
        "labels": {m.key: m.label for m in metrics},
    })
