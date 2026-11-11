from django.conf import settings
from django.db import models

from apps.core.models import TimeStamped


class IntelligenceCategory(TimeStamped):
    """Database-driven category (Good Governance, Human Rights …).

    Six independent switches. Turning any of them off never deletes data – it only
    changes what is collected, scored, ranked, shown or printed.
    """
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=120, unique=True)
    description = models.TextField(blank=True)
    methodology = models.TextField(blank=True, help_text="Category-specific methodology shown on the public site.")
    display_order = models.PositiveSmallIntegerField(default=0)
    icon = models.CharField(max_length=40, blank=True)

    is_enabled = models.BooleanField("Master enable", default=True)
    collection_enabled = models.BooleanField("Data collection", default=True)
    scoring_enabled = models.BooleanField("Scoring", default=True)
    public_visible = models.BooleanField("Public visibility", default=True)
    ranking_included = models.BooleanField("Ranking inclusion", default=True)
    pdf_included = models.BooleanField("PDF report inclusion", default=True)

    activation_date = models.DateField(null=True, blank=True)
    version = models.PositiveIntegerField(default=1, editable=False)

    class Meta:
        ordering = ["display_order", "name"]
        verbose_name_plural = "intelligence categories"

    def __str__(self):
        return self.name

    # Effective flags: master switch gates everything else.
    @property
    def collects(self):
        return self.is_enabled and self.collection_enabled

    @property
    def scores(self):
        return self.is_enabled and self.scoring_enabled

    @property
    def visible(self):
        return self.is_enabled and self.public_visible

    @property
    def ranked(self):
        return self.is_enabled and self.scoring_enabled and self.ranking_included

    @property
    def in_pdf(self):
        return self.is_enabled and self.pdf_included

    def save(self, *args, **kwargs):
        if self.pk:
            old = type(self).objects.filter(pk=self.pk).first()
            if old and any(getattr(old, f) != getattr(self, f) for f in self.VERSIONED_FIELDS):
                self.version = old.version + 1
                super().save(*args, **kwargs)
                CategoryVersion.snapshot(self)
                return
        super().save(*args, **kwargs)
        if not CategoryVersion.objects.filter(category=self).exists():
            CategoryVersion.snapshot(self)

    VERSIONED_FIELDS = ["name", "description", "methodology", "is_enabled", "collection_enabled", "scoring_enabled",
                        "public_visible", "ranking_included", "pdf_included", "activation_date"]


class CategoryVersion(models.Model):
    """Immutable history of every category configuration change."""
    category = models.ForeignKey(IntelligenceCategory, on_delete=models.CASCADE, related_name="versions")
    version = models.PositiveIntegerField()
    snapshot_data = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["category", "-version"]
        unique_together = [("category", "version")]

    @classmethod
    def snapshot(cls, cat):
        from apps.core.audit import get_current_user
        data = {f: str(getattr(cat, f)) if getattr(cat, f) is not None else None for f in IntelligenceCategory.VERSIONED_FIELDS}
        cls.objects.get_or_create(category=cat, version=cat.version,
                                  defaults={"snapshot_data": data, "created_by": get_current_user()})


class Indicator(TimeStamped):
    """A measurable variable inside a category (e.g. CPI score, journalists killed)."""
    DIRECTION = [("higher_better", "Higher is better"), ("lower_better", "Lower is better")]
    VALUE_TYPE = [("score", "Score / index"), ("count", "Count"), ("rate", "Rate / percent"), ("rank", "Rank position"),
                  ("currency", "Currency"), ("ratio", "Ratio")]
    category = models.ForeignKey(IntelligenceCategory, on_delete=models.PROTECT, related_name="indicators")
    code = models.SlugField(max_length=80, unique=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    unit = models.CharField(max_length=40, blank=True)
    value_type = models.CharField(max_length=10, choices=VALUE_TYPE, default="score")
    direction = models.CharField(max_length=14, choices=DIRECTION, default="higher_better")
    scale_min = models.FloatField(null=True, blank=True, help_text="Theoretical minimum used for normalisation (blank = use observed min).")
    scale_max = models.FloatField(null=True, blank=True, help_text="Theoretical maximum used for normalisation (blank = use observed max).")
    per_capita = models.BooleanField(default=False, help_text="Divide by population (per million) before normalising counts.")
    TRANSFORM = [("none", "None"), ("log", "log(1 + x) before normalisation (skewed rates)")]
    transform = models.CharField(max_length=4, choices=TRANSFORM, default="none")
    weight_in_category = models.FloatField(default=1.0)
    primary_source = models.ForeignKey("sources.DataSource", null=True, blank=True, on_delete=models.SET_NULL, related_name="indicators")
    is_active = models.BooleanField(default=True)
    used_in_scoring = models.BooleanField(default=True)
    display_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["category", "display_order", "name"]

    def __str__(self):
        return f"{self.category.name} › {self.name}"
