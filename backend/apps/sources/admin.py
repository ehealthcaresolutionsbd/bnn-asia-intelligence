from django.contrib import admin, messages

from .models import DataCollectionLog, DataSource, SourceDataset
from .services import sync_source, test_source


@admin.register(DataSource)
class DataSourceAdmin(admin.ModelAdmin):
    list_display = ("name", "method", "kind", "status", "is_active", "reliability", "last_test_at", "last_success_at")
    list_filter = ("status", "method", "kind", "is_active")
    list_editable = ("is_active",)
    search_fields = ("name", "organisation")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("last_sync_at", "last_success_at", "last_test_at", "last_test_message")
    actions = ["run_test", "run_sync"]

    @admin.action(description="Test connection")
    def run_test(self, request, qs):
        for s in qs:
            ok = test_source(s)
            self.message_user(request, f"{s.name}: {s.last_test_message}", messages.SUCCESS if ok else messages.WARNING)

    @admin.action(description="Synchronise now")
    def run_sync(self, request, qs):
        for s in qs:
            log = sync_source(s, triggered_by=f"admin:{request.user}")
            self.message_user(request, f"{s.name}: {log.status} ({log.items_created} new) {log.message[:200]}",
                              messages.SUCCESS if log.status == "success" else messages.WARNING)


@admin.register(DataCollectionLog)
class DataCollectionLogAdmin(admin.ModelAdmin):
    list_display = ("source", "started_at", "status", "items_fetched", "items_created", "items_skipped", "triggered_by")
    list_filter = ("status", "source")
    readonly_fields = [f.name for f in DataCollectionLog._meta.fields]


admin.site.register(SourceDataset)
