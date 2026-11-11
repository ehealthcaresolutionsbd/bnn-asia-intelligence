from django.core.exceptions import ValidationError
from django.db import models

from apps.core.models import TimeStamped


class IndicatorObservation(TimeStamped):
    """One value of one indicator for one country for one reference period.

    Missing data is represented by the *absence* of a row – never by 0.
    """
    STATUS = [("estimated", "Estimated"), ("preliminary", "Preliminary"), ("final", "Final")]
    VERIFY = [("pending", "Pending"), ("verified", "Verified"), ("disputed", "Disputed"), ("rejected", "Rejected")]

    indicator = models.ForeignKey("catalog.Indicator", on_delete=models.PROTECT, related_name="observations")
    country = models.ForeignKey("core.Country", on_delete=models.PROTECT, related_name="observations")
    reporting_period = models.ForeignKey("core.ReportingPeriod", on_delete=models.PROTECT, related_name="observations",
                                         help_text="Edition this value counts towards. Historical reference values use is_historical.")
    value = models.FloatField()
    reference_start = models.DateField(help_text="Start of the period the value describes (e.g. 2025-01-01).")
    reference_end = models.DateField(help_text="End of the period the value describes.")
    reference_label = models.CharField(max_length=40, help_text="Human label, e.g. 'CPI 2025' or 'FY2025-26'.")
    data_status = models.CharField(max_length=12, choices=STATUS, default="final")
    is_historical = models.BooleanField(default=False, help_text="Historical reference only – excluded from scores and rankings.")
    published_rank = models.PositiveIntegerField(null=True, blank=True, help_text="Global rank as published by the source, if any.")
    published_rank_of = models.PositiveIntegerField(null=True, blank=True)

    source = models.ForeignKey("sources.DataSource", on_delete=models.PROTECT, related_name="observations")
    dataset = models.ForeignKey("sources.SourceDataset", null=True, blank=True, on_delete=models.SET_NULL)
    source_url = models.URLField(max_length=500)
    published_at = models.DateField(null=True, blank=True)
    collected_at = models.DateTimeField()
    verified_at = models.DateTimeField(null=True, blank=True)
    verification_status = models.CharField(max_length=10, choices=VERIFY, default="pending")
    verified_by = models.ForeignKey("auth.User", null=True, blank=True, on_delete=models.SET_NULL)
    notes = models.TextField(blank=True)
    ci_low = models.FloatField(null=True, blank=True, help_text="Lower bound of the 90% uncertainty interval (computed statistics only).")
    ci_high = models.FloatField(null=True, blank=True, help_text="Upper bound of the 90% uncertainty interval.")
    sample_size = models.PositiveIntegerField(null=True, blank=True, help_text="Number of events/records the value is computed from.")

    class Meta:
        ordering = ["indicator", "country", "-reference_end"]
        constraints = [
            models.UniqueConstraint(fields=["indicator", "country", "reporting_period", "reference_label", "source"],
                                    name="uniq_observation_per_ref"),
            models.CheckConstraint(condition=models.Q(reference_end__gte=models.F("reference_start")), name="obs_ref_order"),
        ]
        indexes = [models.Index(fields=["country", "reporting_period"]), models.Index(fields=["indicator", "reporting_period"])]

    def __str__(self):
        return f"{self.country.iso3} {self.indicator.code} {self.reference_label}: {self.value}"

    def clean(self):
        p = self.reporting_period
        if p and not self.is_historical and not (p.start_date <= self.reference_end and self.reference_start <= p.end_date):
            # Indexes published during the period about the previous year are allowed only if flagged and labelled.
            if not self.notes:
                raise ValidationError("Reference period lies outside the reporting period. Mark as historical or explain "
                                      "in notes why it is the latest available value for this edition.")

    @property
    def counts_for_scoring(self):
        return (not self.is_historical) and self.verification_status == "verified"
