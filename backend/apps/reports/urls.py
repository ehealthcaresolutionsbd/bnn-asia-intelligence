from django.urls import path

from .views import report_pdf

urlpatterns = [path("<int:pk>.pdf", report_pdf, name="report-pdf")]
