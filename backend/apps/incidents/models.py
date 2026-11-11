"""Incident monitoring: one Incident = one real-world event, many claims & evidence.

Several articles reporting the same arrest create several *claims* attached to a
single incident, so counts are never inflated. Conflicting numbers are preserved
as separate claims; the incident stores reported_min/max rather than silently
picking one figure.
"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.core.models import TimeStamped

VERIFICATION_STATES = [("pending", "Pending"), ("under_review", "Under review"), ("verified", "Verified"),
                       ("disputed", "Disputed"), ("rejected", "Rejected")]
CONFIDENCE = [("low", "Low"), ("medium", "Medium"), ("high", "High")]


class IncidentType(TimeStamped):
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=120, unique=True)
    category = models.ForeignKey("catalog.IntelligenceCategory", on_delete=models.PROTECT, related_name="incident_types")
    is_sensitive = models.BooleanField(default=True, help_text="Sensitive types always need two-person review before publication.")
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["category", "name"]

    def __str__(self):
        return self.name


class NewsArticle(TimeStamped):
    """Raw collected item (RSS/API). Stores metadata + short excerpt only, never full copyrighted text."""
    source = models.ForeignKey("sources.DataSource", on_delete=models.PROTECT, related_name="articles")
    url = models.URLField(max_length=700, unique=True)
    title = models.CharField(max_length=500)
    excerpt = models.TextField(blank=True, help_text="Feed-provided summary (≤ 600 chars).")
    published_at = models.DateTimeField(null=True, blank=True)
    collected_at = models.DateTimeField()
    detected_countries = models.ManyToManyField("core.Country", blank=True, related_name="articles")
    detected_types = models.ManyToManyField(IncidentType, blank=True, related_name="articles")
    ai_summary = models.TextField(blank=True)
    ai_extracted = models.JSONField(default=dict, blank=True, help_text="Machine suggestions (dates, numbers). Advisory only.")
    triage_status = models.CharField(max_length=12, default="new",
                                     choices=[("new", "New"), ("relevant", "Relevant"), ("irrelevant", "Irrelevant"),
                                              ("linked", "Linked to incident")])
    content_hash = models.CharField(max_length=64, db_index=True)

    class Meta:
        ordering = ["-published_at"]

    def __str__(self):
        return self.title[:90]


class Incident(TimeStamped):
    country = models.ForeignKey("core.Country", on_delete=models.PROTECT, related_name="incidents")
    incident_type = models.ForeignKey(IncidentType, on_delete=models.PROTECT, related_name="incidents")
    reporting_period = models.ForeignKey("core.ReportingPeriod", on_delete=models.PROTECT, related_name="incidents")
    title = models.CharField(max_length=300)
    description = models.TextField()
    event_date = models.DateField(help_text="When the event happened (NOT when it was reported).")
    event_date_precision = models.CharField(max_length=6, default="day", choices=[("day", "Day"), ("month", "Month"), ("year", "Year")])
    location = models.CharField(max_length=200, blank=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    victims_reported_min = models.PositiveIntegerField(null=True, blank=True)
    victims_reported_max = models.PositiveIntegerField(null=True, blank=True)
    victims_verified = models.PositiveIntegerField(null=True, blank=True, help_text="Figure confirmed by the reviewer, if any.")
    verification_status = models.CharField(max_length=12, choices=VERIFICATION_STATES, default="pending")
    confidence = models.CharField(max_length=6, choices=CONFIDENCE, default="low")
    is_published = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)
    first_reported_at = models.DateTimeField(null=True, blank=True)
    collected_at = models.DateTimeField(null=True, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    duplicate_of = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="duplicates")

    class Meta:
        ordering = ["-event_date"]
        indexes = [models.Index(fields=["country", "reporting_period", "verification_status"])]

    def __str__(self):
        return f"{self.country.iso3} {self.event_date} {self.title[:60]}"

    def clean(self):
        p = self.reporting_period
        if p and self.event_date and not p.contains(self.event_date):
            raise ValidationError({"event_date": f"Event date {self.event_date} is outside the {p.name} reporting period. "
                                                 "Incidents are filed under the period in which they occurred."})
        if self.is_published:
            if self.verification_status != "verified":
                raise ValidationError("Only verified incidents can be published.")
            if self.incident_type_id and self.incident_type.is_sensitive and (
                    not self.approved_by_id or self.approved_by_id == self.created_by_id):
                raise ValidationError("Sensitive incidents need approval by a second person (not the creator).")
        if self.victims_reported_min and self.victims_reported_max and self.victims_reported_min > self.victims_reported_max:
            raise ValidationError("Reported minimum exceeds maximum.")

    @property
    def counts(self):
        """Counts towards statistics only when verified, not a duplicate, and in-period."""
        return self.verification_status == "verified" and self.duplicate_of_id is None

    def refresh_reported_range(self):
        nums = [c.reported_number for c in self.claims.exclude(status="rejected") if c.reported_number is not None]
        self.victims_reported_min = min(nums) if nums else None
        self.victims_reported_max = max(nums) if nums else None
        self.save(update_fields=["victims_reported_min", "victims_reported_max", "updated_at"])


class IncidentClaim(TimeStamped):
    """What one source says about an incident. Conflicting figures are kept side by side."""
    incident = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name="claims")
    source = models.ForeignKey("sources.DataSource", on_delete=models.PROTECT, related_name="claims")
    article = models.ForeignKey(NewsArticle, null=True, blank=True, on_delete=models.SET_NULL, related_name="claims")
    source_url = models.URLField(max_length=700)
    claim_text = models.TextField(help_text="Paraphrase of what the source reports.")
    reported_number = models.PositiveIntegerField(null=True, blank=True)
    reported_event_date = models.DateField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    collected_at = models.DateTimeField()
    status = models.CharField(max_length=12, choices=VERIFICATION_STATES, default="pending")

    class Meta:
        ordering = ["incident", "published_at"]
        unique_together = [("incident", "source_url")]

    def __str__(self):
        return f"Claim by {self.source} on {self.incident_id}"


class IncidentEvidence(TimeStamped):
    KIND = [("document", "Document"), ("photo", "Photo"), ("video", "Video"), ("testimony", "Testimony"),
            ("official", "Official statement"), ("court", "Court record"), ("link", "Web link")]
    incident = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name="evidence")
    kind = models.CharField(max_length=10, choices=KIND)
    description = models.TextField()
    url = models.URLField(max_length=700, blank=True)
    file = models.FileField(upload_to="evidence/%Y/%m/", blank=True)
    is_public = models.BooleanField(default=False, help_text="Private by default – may identify witnesses.")
    validated = models.BooleanField(default=False)
    validated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        verbose_name_plural = "incident evidence"


class VerificationTask(TimeStamped):
    KIND = [("triage_article", "Triage article"), ("verify_incident", "Verify incident"), ("verify_observation", "Verify observation"),
            ("resolve_duplicate", "Resolve duplicate"), ("resolve_conflict", "Resolve conflicting numbers"), ("editorial", "Editorial review")]
    STATUS = [("open", "Open"), ("in_progress", "In progress"), ("done", "Done"), ("cancelled", "Cancelled")]
    kind = models.CharField(max_length=20, choices=KIND)
    status = models.CharField(max_length=12, choices=STATUS, default="open")
    priority = models.PositiveSmallIntegerField(default=3)
    incident = models.ForeignKey(Incident, null=True, blank=True, on_delete=models.CASCADE, related_name="tasks")
    article = models.ForeignKey(NewsArticle, null=True, blank=True, on_delete=models.CASCADE, related_name="tasks")
    observation = models.ForeignKey("observations.IndicatorObservation", null=True, blank=True, on_delete=models.CASCADE, related_name="tasks")
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    due_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    resolution = models.TextField(blank=True)

    class Meta:
        ordering = ["status", "priority", "-created_at"]

    def __str__(self):
        return f"{self.get_kind_display()} #{self.pk}"
