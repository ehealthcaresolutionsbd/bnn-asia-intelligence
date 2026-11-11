from django.conf import settings
from django.db import models

from apps.core.models import TimeStamped

SECTIONS = [
    ("overview", "Country Overview"), ("executive_summary", "Executive Summary"), ("good-governance", "Good Governance"),
    ("human-rights", "Human Rights"), ("press-freedom", "Press Freedom"), ("rule-of-law", "Rule of Law"),
    ("economic-social", "Economic Conditions"), ("incidents", "Major Incidents"), ("trends", "Trends within the period"),
    ("findings", "Key Findings"), ("sources", "Sources and References"), ("methodology", "Methodology and Limitations"),
]


class CountryReport(TimeStamped):
    """Structured country report. Draft text may be AI-assisted but every claim must cite a verified record."""
    STATUS = [("draft", "Draft"), ("review", "In editorial review"), ("published", "Published"),
              ("superseded", "Superseded by a newer version")]
    PUBLIC_STATUSES = ("published", "superseded")
    country = models.ForeignKey("core.Country", on_delete=models.PROTECT, related_name="reports")
    reporting_period = models.ForeignKey("core.ReportingPeriod", on_delete=models.PROTECT, related_name="reports")
    snapshot = models.ForeignKey("rankings.RankingSnapshot", null=True, blank=True, on_delete=models.PROTECT)
    title = models.CharField(max_length=250)
    sections = models.JSONField(default=dict, help_text="{section_key: {'text': str, 'citations': [record refs]}}")
    status = models.CharField(max_length=10, choices=STATUS, default="draft")
    version = models.PositiveIntegerField(default=1)
    generated_with_ai = models.BooleanField(default=False)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    editor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    published_at = models.DateTimeField(null=True, blank=True)
    pdf = models.FileField(upload_to="reports/%Y/", blank=True)
    locked = models.BooleanField(
        default=False, help_text="Locked by an editor: automatic regeneration skips this country/period while the "
                                 "latest version is locked. Set automatically when an editor changes section text.")

    class Meta:
        ordering = ["-reporting_period__start_date", "country__name", "-version"]
        unique_together = [("country", "reporting_period", "version")]

    def __str__(self):
        return f"{self.title} (v{self.version})"

    @property
    def is_public(self):
        return self.status in self.PUBLIC_STATUSES

    def ordered_sections(self):
        """[(key, section_dict)] in display order. Works for legacy reports without '_meta'."""
        secs = self.sections or {}
        order = (secs.get("_meta") or {}).get("order") or [k for k, _ in SECTIONS]
        labels = dict(SECTIONS)
        out = []
        for k in order + [k for k in secs if k not in order]:
            sec = secs.get(k)
            if k.startswith("_") or k == "charts" or not isinstance(sec, dict) or any(k == o for o, _ in out):
                continue
            sec = dict(sec)
            sec.setdefault("title", labels.get(k, k.replace("-", " ").title()))
            out.append((k, sec))
        return out

    @property
    def charts(self):
        c = (self.sections or {}).get("charts")
        return c if isinstance(c, list) else []
