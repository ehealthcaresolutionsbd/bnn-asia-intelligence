from django.contrib import admin

from .models import CategoryVersion, Indicator, IntelligenceCategory


class IndicatorInline(admin.TabularInline):
    model = Indicator
    extra = 0
    fields = ("code", "name", "direction", "scale_min", "scale_max", "weight_in_category", "is_active", "used_in_scoring")


class VersionInline(admin.TabularInline):
    model = CategoryVersion
    extra = 0
    can_delete = False
    readonly_fields = ("version", "snapshot_data", "created_at", "created_by")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(IntelligenceCategory)
class IntelligenceCategoryAdmin(admin.ModelAdmin):
    """Super Admin category console: every switch is editable from the list view.
    Switching off never deletes data."""
    list_display = ("name", "display_order", "is_enabled", "collection_enabled", "scoring_enabled", "public_visible",
                    "ranking_included", "pdf_included", "version", "activation_date")
    list_editable = ("display_order", "is_enabled", "collection_enabled", "scoring_enabled", "public_visible",
                     "ranking_included", "pdf_included")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [IndicatorInline, VersionInline]
    readonly_fields = ("version",)
    actions = ["enable_all", "disable_master"]

    def has_delete_permission(self, request, obj=None):
        return False  # categories are disabled, never deleted

    @admin.action(description="Enable selected (all switches on)")
    def enable_all(self, request, qs):
        for c in qs:
            for f in ("is_enabled", "collection_enabled", "scoring_enabled", "public_visible", "ranking_included", "pdf_included"):
                setattr(c, f, True)
            c.save()

    @admin.action(description="Disable selected (master off – data kept)")
    def disable_master(self, request, qs):
        for c in qs:
            c.is_enabled = False
            c.save()


@admin.register(Indicator)
class IndicatorAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "category", "direction", "weight_in_category", "primary_source", "is_active", "used_in_scoring")
    list_editable = ("weight_in_category", "is_active", "used_in_scoring")
    list_filter = ("category", "is_active", "used_in_scoring", "value_type")
    search_fields = ("code", "name")
