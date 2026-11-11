from django import forms
from django.contrib import admin, messages
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html

from .models import CountryReport

PREFIX = "section__"


class CountryReportForm(forms.ModelForm):
    """One textarea per report section, so editors edit prose without touching the JSON structure."""

    class Meta:
        model = CountryReport
        fields = ["title", "status", "locked", "editor"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for key, sec in (self.instance.ordered_sections() if self.instance.pk else []):
            if "text" not in sec or sec.get("kind") == "sources":
                continue
            self.fields[PREFIX + key] = forms.CharField(
                label=sec["title"], required=False, initial=sec.get("text", ""),
                widget=forms.Textarea(attrs={"rows": 8 if sec.get("kind") != "methodology" else 14, "style": "width:95%"}),
                help_text="Keep the [n] citation markers – they refer to the numbered sources of this section.")

    def changed_sections(self):
        return [n[len(PREFIX):] for n in self.changed_data if n.startswith(PREFIX)]


@admin.register(CountryReport)
class CountryReportAdmin(admin.ModelAdmin):
    form = CountryReportForm
    list_display = ("title", "country", "reporting_period", "version", "status", "locked", "published_at", "links")
    list_editable = ("locked",)
    list_filter = ("status", "locked", "reporting_period", "country__region")
    search_fields = ("title", "country__name", "country__iso3")
    readonly_fields = ("country", "reporting_period", "snapshot", "version", "author", "published_at", "links",
                       "created_at", "updated_at")
    actions = ["regenerate", "lock", "unlock"]

    def has_add_permission(self, request):
        return False   # reports are generated (builder / generate_reports), then edited here

    def get_fieldsets(self, request, obj=None):
        base = [(None, {"fields": ["title", "country", "reporting_period", "version", "status", "locked", "links",
                                   "snapshot", "author", "editor", "published_at", "created_at", "updated_at"]})]
        form = self.get_form(request, obj)(instance=obj) if obj else None
        secs = [f for f in (form.fields if form else {}) if f.startswith(PREFIX)]
        if secs:
            base.append(("Section text (editing a section locks the report against automatic regeneration)",
                         {"fields": secs}))
        return base

    def get_form(self, request, obj=None, change=False, **kwargs):
        kwargs["fields"] = ["title", "status", "locked", "editor"]
        return super().get_form(request, obj, change=change, **kwargs)

    @admin.display(description="View")
    def links(self, obj):
        if not obj.pk:
            return "–"
        return format_html('<a href="{}" target="_blank">HTML</a> · <a href="{}" target="_blank">PDF</a>',
                           reverse("report-html", args=[obj.pk]), reverse("report-pdf", args=[obj.pk]))

    def save_model(self, request, obj, form, change):
        changed = form.changed_sections() if hasattr(form, "changed_sections") else []
        if changed:
            sections = dict(obj.sections)
            for key in changed:
                sec = dict(sections.get(key) or {})
                sec["text"] = form.cleaned_data[PREFIX + key]
                sec["edited"] = True
                sections[key] = sec
            meta = dict(sections.get("_meta") or {})
            meta["edited_at"] = timezone.now().isoformat()
            meta["edited_sections"] = sorted(set(meta.get("edited_sections", [])) | set(changed))
            sections["_meta"] = meta
            obj.sections = sections
            obj.editor = request.user
            obj.locked = True
        becomes_published = obj.status == "published" and (not change or "status" in form.changed_data)
        if becomes_published and not obj.published_at:
            obj.published_at = timezone.now()
        super().save_model(request, obj, form, change)
        if becomes_published:
            from .builder import supersede_older
            supersede_older(obj)
        if changed:
            messages.info(request, "Section text saved; the report is now locked against automatic regeneration.")

    @admin.action(description="Regenerate (new version)")
    def regenerate(self, request, queryset):
        from .builder import build_report
        done, skipped = 0, []
        for pair in sorted({(r.country_id, r.reporting_period_id) for r in queryset}):
            r = queryset.filter(country_id=pair[0], reporting_period_id=pair[1]).select_related("country", "reporting_period").first()
            new = build_report(r.country, r.reporting_period, author=request.user, publish=True)
            if new.skipped_locked:
                skipped.append(str(r.country))
            else:
                done += 1
        if done:
            self.message_user(request, f"{done} report(s) regenerated as new published versions.", messages.SUCCESS)
        if skipped:
            self.message_user(request, f"Skipped (latest version locked): {', '.join(skipped)}. Unlock first to regenerate.",
                              messages.WARNING)

    @admin.action(description="Lock (protect from regeneration)")
    def lock(self, request, queryset):
        for r in queryset:
            r.locked = True
            r.save(update_fields=["locked", "updated_at"])
        self.message_user(request, f"{queryset.count()} report(s) locked.")

    @admin.action(description="Unlock (allow regeneration)")
    def unlock(self, request, queryset):
        for r in queryset:
            r.locked = False
            r.save(update_fields=["locked", "updated_at"])
        self.message_user(request, f"{queryset.count()} report(s) unlocked.")
