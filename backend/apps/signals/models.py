from django.conf import settings
from django.db import models


class IngestedDay(models.Model):
    """One GDELT daily export processed (idempotency + audit)."""
    day = models.DateField(unique=True)
    source_url = models.URLField()
    rows_total = models.PositiveIntegerField(default=0)
    rows_asia = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=10, default="ok", choices=[("ok", "OK"), ("failed", "Failed"), ("missing", "Missing upstream")])
    message = models.TextField(blank=True)
    processed_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-day"]


class CountryVolumeDaily(models.Model):
    """All GDELT events located in a country on a day – denominator for coverage-bias correction."""
    country = models.ForeignKey("core.Country", on_delete=models.CASCADE, related_name="volume")
    day = models.DateField(db_index=True)
    events = models.PositiveIntegerField(default=0)
    articles = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = [("country", "day")]


class SignalDaily(models.Model):
    """Aggregate of one BNN signal (see rules.SIGNALS) for one country and one EVENT day."""
    country = models.ForeignKey("core.Country", on_delete=models.CASCADE, related_name="signals")
    day = models.DateField(db_index=True)
    signal = models.CharField(max_length=40, db_index=True)
    events = models.PositiveIntegerField(default=0)
    mentions = models.PositiveIntegerField(default=0)
    sources = models.PositiveIntegerField(default=0)
    articles = models.PositiveIntegerField(default=0)
    goldstein_sum = models.FloatField(default=0)
    tone_sum = models.FloatField(default=0)
    sample_urls = models.JSONField(default=list, blank=True, help_text="Up to 5 source article URLs (evidence trail).")

    class Meta:
        unique_together = [("country", "day", "signal")]
        indexes = [models.Index(fields=["signal", "day"])]


class EditorialAdjustment(models.Model):
    """BNN editors may override or annotate a computed result. Always shown publicly with the reason."""
    KIND = [("note", "Annotation only"), ("override", "Override score"), ("exclude", "Exclude country from ranking")]
    reporting_period = models.ForeignKey("core.ReportingPeriod", on_delete=models.PROTECT)
    country = models.ForeignKey("core.Country", on_delete=models.PROTECT)
    category = models.ForeignKey("catalog.IntelligenceCategory", null=True, blank=True, on_delete=models.PROTECT,
                                 help_text="Blank = overall index.")
    kind = models.CharField(max_length=10, choices=KIND, default="note")
    score = models.FloatField(null=True, blank=True, help_text="Replacement 0–100 score (override only).")
    reason = models.TextField(help_text="Public explanation – required.")
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_kind_display()} – {self.country} ({self.category or 'overall'})"
