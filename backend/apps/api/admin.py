from django.contrib import admin, messages

from .models import ApiClient


@admin.register(ApiClient)
class ApiClientAdmin(admin.ModelAdmin):
    list_display = ("name", "key_prefix", "is_active", "created_at", "last_used_at")
    readonly_fields = ("key_prefix", "created_at", "last_used_at")

    def save_model(self, request, obj, form, change):
        if not change:
            new, key = ApiClient.issue(obj.name)
            obj.pk, obj.key_prefix, obj.key_hash = new.pk, new.key_prefix, new.key_hash
            self.message_user(request, f"API key (shown once – copy it into the WordPress plugin now): {key}", messages.WARNING)
            return
        super().save_model(request, obj, form, change)
