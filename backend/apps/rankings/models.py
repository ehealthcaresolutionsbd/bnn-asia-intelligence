from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.core.models import TimeStamped


class RankingMethodology(TimeStamped):
    """Versioned methodology for the BNN Asia Index. Published versions are frozen."""
    MODE = [("strict", "Strict weight – overall unavailable if a weighted category is disabled"),
            ("auto", "Auto reweight – remaining categories rescaled proportionally"),
            ("custom", "Custom weight – Super Admin weights used as entered")]
    name = models.CharField(max_length=120, default="BNN Asia Index")
    version = models.CharField(max_length=20, help_text="Semantic version, e.g. 1.0.0")
    reporting_period = models.ForeignKey("core.ReportingPeriod", on_delete=models.PROTECT, related_name="methodologies")
    mode = models.CharField(max_length=8, choices=MODE, default="auto")
    min_coverage = models.FloatField(default=0.6, help_text="Minimum share (0–1) of total weight that must have data to be ranked.")
    min_category_coverage = models.FloatField(default=0.5, help_text="Minimum share of a category's indicator weight needed to score that category.")
    description = models.TextField(blank=True)
    limitations = models.TextField(blank=True)
    is_published = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["-reporting_period__start_date", "-created_at"]
        unique_together = [("name", "version", "reporting_period")]
        verbose_name_plural = "ranking methodologies"

    def __str__(self):
        return f"{self.name} v{self.version} ({self.reporting_period})"

    def save(self, *args, **kwargs):
        if self.pk:
            old = type(self).objects.get(pk=self.pk)
            if old.is_published:
                raise ValidationError("Published methodologies are frozen. Create a new version instead.")
        super().save(*args, **kwargs)


class MethodologyWeight(models.Model):
    methodology = models.ForeignKey(RankingMethodology, on_delete=models.CASCADE, related_name="weights")
    category = models.ForeignKey("catalog.IntelligenceCategory", on_delete=models.PROTECT)
    weight = models.FloatField(help_text="Percentage points, e.g. 25 for 25%.")

    class Meta:
        unique_together = [("methodology", "category")]
        ordering = ["-weight"]

    def __str__(self):
        return f"{self.category}: {self.weight}%"

    def save(self, *args, **kwargs):
        if self.methodology.is_published:
            raise ValidationError("Cannot change weights of a published methodology.")
        super().save(*args, **kwargs)


class RankingSnapshot(TimeStamped):
    """A frozen calculation result. Published snapshots can never be edited or deleted."""
    STATUS = [("draft", "Draft"), ("published", "Published"), ("superseded", "Superseded")]
    methodology = models.ForeignKey(RankingMethodology, on_delete=models.PROTECT, related_name="snapshots")
    reporting_period = models.ForeignKey("core.ReportingPeriod", on_delete=models.PROTECT, related_name="snapshots")
    status = models.CharField(max_length=10, choices=STATUS, default="draft")
    calculated_at = models.DateTimeField()
    published_at = models.DateTimeField(null=True, blank=True)
    effective_weights = models.JSONField(default=dict)
    overall_available = models.BooleanField(default=True)
    unavailable_reason = models.TextField(blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-calculated_at"]

    def __str__(self):
        return f"Snapshot {self.pk} {self.methodology} [{self.status}]"

    def delete(self, *args, **kwargs):
        if self.status != "draft":
            raise ValidationError("Published snapshots cannot be deleted.")
        super().delete(*args, **kwargs)


class CountryScore(models.Model):
    """Per-country, per-category (category=None → overall) result inside one snapshot."""
    snapshot = models.ForeignKey(RankingSnapshot, on_delete=models.CASCADE, related_name="scores")
    country = models.ForeignKey("core.Country", on_delete=models.PROTECT, related_name="scores")
    category = models.ForeignKey("catalog.IntelligenceCategory", null=True, blank=True, on_delete=models.PROTECT)
    score = models.FloatField(null=True, blank=True)
    rank = models.PositiveIntegerField(null=True, blank=True)
    previous_rank = models.PositiveIntegerField(null=True, blank=True)
    coverage = models.FloatField(default=0.0)
    confidence = models.CharField(max_length=6, default="low")
    is_ranked = models.BooleanField(default=False)
    status_label = models.CharField(max_length=60, blank=True)
    imputed_categories = models.JSONField(default=list, blank=True)
    detail = models.JSONField(default=dict, blank=True, help_text="Indicator-level inputs and normalised values.")

    class Meta:
        unique_together = [("snapshot", "country", "category")]
        ordering = ["snapshot", "category", "rank"]

    @property
    def position_change(self):
        if self.rank and self.previous_rank:
            return self.previous_rank - self.rank
        return None
