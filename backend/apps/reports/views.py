import base64
import logging
from pathlib import Path

from django.conf import settings
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.dateparse import parse_datetime
from django.views.static import serve

from .charts import CHART_DIR
from .models import CountryReport


def chart_root() -> Path:
    return (Path(settings.MEDIA_ROOT) / CHART_DIR).resolve()


def _visible_report(request, pk):
    report = get_object_or_404(CountryReport.objects.select_related("country", "reporting_period", "editor"), pk=pk)
    if not report.is_public and not (request.user.is_authenticated and request.user.is_staff):
        raise Http404
    return report


def _chart_src(path, mode):
    """PDF: embed as data URI (works regardless of WeasyPrint base_url); web: URL served from /reports/charts/."""
    name = Path(path).name
    file = chart_root() / name
    if not file.is_file():
        return None
    if mode == "pdf":
        return "data:image/png;base64," + base64.b64encode(file.read_bytes()).decode()
    return reverse("report-chart", args=[name])


def report_context(report, mode):
    charts_by_sec = {}
    for ch in report.charts:
        src = _chart_src(ch.get("path", ""), mode)
        if src:
            charts_by_sec.setdefault(ch.get("section") or "executive_summary", []).append({**ch, "src": src})
    sections = []
    for key, sec in report.ordered_sections():
        sec["paragraphs"] = [p.strip() for p in (sec.get("text") or "").split("\n") if p.strip()]
        sec["charts"] = charts_by_sec.get(key, [])
        sec["signal_rows"] = [{**s, "events_fmt": f"{s['events']:,}"} for s in sec.get("signals", []) if s.get("events")]
        sections.append((key, sec))
    meta = (report.sections or {}).get("_meta") or {}
    return {"report": report, "sections": sections, "mode": mode,
            "generated_at": parse_datetime(meta.get("generated_at") or "") or report.created_at,
            "methodology_version": meta.get("methodology_version") or (
                report.snapshot.methodology.version if report.snapshot_id else None),
            "pdf_url": reverse("report-pdf", args=[report.pk])}


def render_pdf(report) -> bytes:
    from weasyprint import HTML
    for name in ("fontTools", "weasyprint"):
        logging.getLogger(name).setLevel(logging.WARNING)   # font subsetting logs are very verbose at INFO
    html = render_to_string("reports/country_report.html", report_context(report, "pdf"))
    return HTML(string=html, base_url=str(settings.BASE_DIR)).write_pdf()


def report_pdf(request, pk):
    report = _visible_report(request, pk)
    resp = HttpResponse(render_pdf(report), content_type="application/pdf")
    resp["Content-Disposition"] = (f'inline; filename="bnn-asia-{report.country.slug}-{report.reporting_period.slug}'
                                   f'-v{report.version}.pdf"')
    return resp


def report_html(request, pk):
    report = _visible_report(request, pk)
    resp = render(request, "reports/country_report_web.html", report_context(report, "web"))
    if not report.is_public:
        resp["X-Robots-Tag"] = "noindex"
    return resp


def report_chart(request, name):
    """Serves only PNG chart files from MEDIA_ROOT/reports/charts (URL pattern restricts the name)."""
    return serve(request, name, document_root=str(chart_root()))
