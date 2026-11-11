from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string

from .models import SECTIONS, CountryReport


def report_pdf(request, pk):
    report = get_object_or_404(CountryReport, pk=pk)
    if report.status != "published" and not (request.user.is_authenticated and request.user.is_staff):
        raise Http404
    from weasyprint import HTML
    order = [k for k, _ in SECTIONS]
    labels = dict(SECTIONS)
    sections = [(labels.get(k, k), report.sections[k]) for k in order if k in report.sections]
    html = render_to_string("reports/country_report.html", {"report": report, "sections": sections})
    pdf = HTML(string=html, base_url=request.build_absolute_uri("/")).write_pdf()
    resp = HttpResponse(pdf, content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="bnn-asia-{report.country.slug}-{report.reporting_period.slug}.pdf"'
    return resp
