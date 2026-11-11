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
    STATUS = [("draft", "Draft"), ("review", "In editorial review"), ("published", "Published")]
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

    class Meta:
        ordering = ["-reporting_period__start_date", "country__name", "-version"]
        unique_together = [("country", "reporting_period", "version")]

    def __str__(self):
        return self.title
