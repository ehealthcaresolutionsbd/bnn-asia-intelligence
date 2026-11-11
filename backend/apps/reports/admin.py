from django.contrib import admin
from django.utils.html import format_html

from .models import CountryReport


@admin.register(CountryReport)
class CountryReportAdmin(admin.ModelAdmin):
    list_display = ("title", "country", "reporting_period", "version", "status", "pdf_link")
    list_filter = ("status", "reporting_period")

    def pdf_link(self, obj):
        return format_html('<a href="/reports/{}.pdf" target="_blank">PDF</a>', obj.pk)
