from django.contrib import admin

from .models import AuditLog, Country, Region, ReportingPeriod


@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = ("name", "parent", "un_m49_code")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Country)
class CountryAdmin(admin.ModelAdmin):
    list_display = ("flag_emoji", "name", "iso3", "region", "is_active", "incident_monitoring")
    list_display_links = ("name",)
    list_editable = ("is_active", "incident_monitoring")
    list_filter = ("region", "is_active", "incident_monitoring")
    search_fields = ("name", "iso3", "aliases")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(ReportingPeriod)
class ReportingPeriodAdmin(admin.ModelAdmin):
    list_display = ("name", "start_date", "end_date", "status", "is_current")
    list_editable = ("status",)
    prepopulated_fields = {"slug": ("name",)}


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("at", "user", "action", "model", "object_repr")
    list_filter = ("action", "model")
    search_fields = ("object_repr", "object_id")
    readonly_fields = [f.name for f in AuditLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
