from django.contrib import admin, messages

from .engine import calculate, publish
from .models import CountryScore, MethodologyWeight, RankingMethodology, RankingSnapshot


class WeightInline(admin.TabularInline):
    model = MethodologyWeight
    extra = 0


@admin.register(RankingMethodology)
class RankingMethodologyAdmin(admin.ModelAdmin):
    list_display = ("name", "version", "reporting_period", "mode", "min_coverage", "is_published")
    inlines = [WeightInline]
    actions = ["run_calculation"]

    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in self.model._meta.fields] if obj and obj.is_published else ["is_published", "published_at"]

    @admin.action(description="Calculate draft snapshot")
    def run_calculation(self, request, qs):
        for m in qs:
            s = calculate(m, note=f"admin:{request.user}")
            self.message_user(request, f"Snapshot {s.pk} – overall available: {s.overall_available}. {s.unavailable_reason}")


class ScoreInline(admin.TabularInline):
    model = CountryScore
    extra = 0
    fields = ("country", "category", "score", "rank", "previous_rank", "coverage", "confidence", "status_label")
    readonly_fields = fields
    can_delete = False


@admin.register(RankingSnapshot)
class RankingSnapshotAdmin(admin.ModelAdmin):
    list_display = ("id", "methodology", "status", "calculated_at", "published_at", "overall_available")
    list_filter = ("status", "reporting_period")
    readonly_fields = [f.name for f in RankingSnapshot._meta.fields]
    inlines = [ScoreInline]
    actions = ["publish_snapshot"]

    @admin.action(description="Publish snapshot (freezes it)")
    def publish_snapshot(self, request, qs):
        for s in qs:
            try:
                publish(s)
                self.message_user(request, f"Published snapshot {s.pk}", messages.SUCCESS)
            except Exception as e:
                self.message_user(request, str(e), messages.ERROR)
