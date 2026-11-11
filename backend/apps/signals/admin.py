from django.contrib import admin

from .models import CountryVolumeDaily, EditorialAdjustment, IngestedDay, SignalDaily
from .rules import SIGNALS


class ReadOnlyAdmin(admin.ModelAdmin):
    """Pipeline output: viewable and filterable, never edited by hand (would break per-file idempotency)."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(IngestedDay)
class IngestedDayAdmin(ReadOnlyAdmin):
    list_display = ("day", "status", "rows_total", "rows_asia", "processed_at")
    list_filter = ("status",)
    date_hierarchy = "day"
    search_fields = ("message",)


@admin.register(CountryVolumeDaily)
class CountryVolumeDailyAdmin(ReadOnlyAdmin):
    list_display = ("day", "country", "events", "articles")
    list_filter = ("country__region", "country")
    list_select_related = ("country",)
    date_hierarchy = "day"
    ordering = ("-day", "country__name")


class SignalFilter(admin.SimpleListFilter):
    title = "signal"
    parameter_name = "signal"

    def lookups(self, request, model_admin):
        return [(k, v[0]) for k, v in SIGNALS.items()]

    def queryset(self, request, qs):
        return qs.filter(signal=self.value()) if self.value() else qs


@admin.register(SignalDaily)
class SignalDailyAdmin(ReadOnlyAdmin):
    list_display = ("day", "country", "signal", "events", "mentions", "sources", "articles", "avg_tone")
    list_filter = (SignalFilter, "country__region", "country")
    list_select_related = ("country",)
    date_hierarchy = "day"
    ordering = ("-day", "country__name", "signal")

    @admin.display(description="Avg tone")
    def avg_tone(self, obj):
        return round(obj.tone_sum / obj.events, 2) if obj.events else None


@admin.register(EditorialAdjustment)
class EditorialAdjustmentAdmin(admin.ModelAdmin):
    list_display = ("country", "category", "kind", "score", "is_active", "reporting_period", "created_by", "created_at")
    list_filter = ("kind", "is_active", "reporting_period", "category")
    search_fields = ("country__name", "reason")
    readonly_fields = ("created_by", "created_at")

    def save_model(self, request, obj, form, change):
        if not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
