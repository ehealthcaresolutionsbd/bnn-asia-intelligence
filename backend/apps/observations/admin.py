from django.contrib import admin
from django.utils import timezone

from .models import IndicatorObservation


@admin.register(IndicatorObservation)
class IndicatorObservationAdmin(admin.ModelAdmin):
    list_display = ("country", "indicator", "value", "reference_label", "data_status", "is_historical",
                    "verification_status", "source", "collected_at")
    list_filter = ("verification_status", "is_historical", "data_status", "indicator__category", "source", "country__region")
    search_fields = ("country__name", "indicator__code", "reference_label")
    autocomplete_fields = ()
    actions = ["mark_verified", "mark_disputed"]

    @admin.action(description="Mark verified")
    def mark_verified(self, request, qs):
        qs.update(verification_status="verified", verified_at=timezone.now(), verified_by=request.user)

    @admin.action(description="Mark disputed")
    def mark_disputed(self, request, qs):
        qs.update(verification_status="disputed")
