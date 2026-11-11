from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import Incident, IncidentClaim, IncidentEvidence, IncidentType, NewsArticle, VerificationTask


class ClaimInline(admin.TabularInline):
    model = IncidentClaim
    extra = 0
    fields = ("source", "source_url", "claim_text", "reported_number", "reported_event_date", "published_at", "collected_at", "status")


class EvidenceInline(admin.TabularInline):
    model = IncidentEvidence
    extra = 0
    fields = ("kind", "description", "url", "file", "is_public", "validated")


@admin.register(Incident)
class IncidentAdmin(admin.ModelAdmin):
    list_display = ("event_date", "country", "incident_type", "title", "victims_reported_min", "victims_reported_max",
                    "verification_status", "confidence", "is_published")
    list_filter = ("verification_status", "is_published", "incident_type__category", "incident_type", "country__region", "country")
    search_fields = ("title", "description", "location")
    date_hierarchy = "event_date"
    inlines = [ClaimInline, EvidenceInline]
    readonly_fields = ("victims_reported_min", "victims_reported_max", "created_by", "reviewed_by", "approved_by",
                       "verified_at", "published_at")
    actions = ["approve_and_publish", "mark_under_review", "mark_disputed"]

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        if obj.verification_status in ("verified", "disputed", "rejected") and not obj.reviewed_by_id:
            obj.reviewed_by, obj.verified_at = request.user, timezone.now()
        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        form.instance.refresh_reported_range()

    @admin.action(description="Approve & publish (second reviewer)")
    def approve_and_publish(self, request, qs):
        for inc in qs:
            inc.approved_by, inc.is_published, inc.published_at = request.user, True, timezone.now()
            try:
                inc.full_clean()
                inc.save()
                self.message_user(request, f"Published: {inc}", messages.SUCCESS)
            except ValidationError as e:
                self.message_user(request, f"Not published – {inc}: {'; '.join(e.messages)}", messages.ERROR)

    @admin.action(description="Mark under review")
    def mark_under_review(self, request, qs):
        qs.update(verification_status="under_review")

    @admin.action(description="Mark disputed")
    def mark_disputed(self, request, qs):
        qs.update(verification_status="disputed", is_published=False)


@admin.register(NewsArticle)
class NewsArticleAdmin(admin.ModelAdmin):
    list_display = ("published_at", "source", "title", "triage_status")
    list_filter = ("triage_status", "source", "detected_countries", "detected_types")
    search_fields = ("title", "excerpt")
    readonly_fields = ("content_hash", "ai_extracted", "collected_at")
    filter_horizontal = ("detected_countries", "detected_types")


@admin.register(VerificationTask)
class VerificationTaskAdmin(admin.ModelAdmin):
    list_display = ("id", "kind", "status", "priority", "article", "incident", "assigned_to", "due_date")
    list_filter = ("kind", "status", "priority")
    list_editable = ("status", "assigned_to")


admin.site.register(IncidentType)
