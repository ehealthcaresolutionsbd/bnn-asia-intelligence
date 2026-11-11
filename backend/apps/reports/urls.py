from django.urls import path, re_path

from .views import report_chart, report_html, report_pdf

urlpatterns = [
    path("<int:pk>.pdf", report_pdf, name="report-pdf"),
    path("<int:pk>/", report_html, name="report-html"),
    # Chart images only: flat file names ending in .png, no directories – see views.report_chart.
    re_path(r"^charts/(?P<name>[A-Za-z0-9][A-Za-z0-9_.-]*\.png)$", report_chart, name="report-chart"),
]
