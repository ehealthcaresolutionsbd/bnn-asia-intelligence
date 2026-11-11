from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class TimeStamped(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Region(TimeStamped):
    """Geographic grouping (Asia → South Asia …). Supports worldwide expansion via parent."""
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=120, unique=True)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="children")
    un_m49_code = models.CharField(max_length=3, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Country(TimeStamped):
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=120, unique=True)
    iso2 = models.CharField(max_length=2, unique=True)
    iso3 = models.CharField(max_length=3, unique=True)
    region = models.ForeignKey(Region, on_delete=models.PROTECT, related_name="countries")
    flag_emoji = models.CharField(max_length=8, blank=True)
    capital = models.CharField(max_length=120, blank=True)
    is_active = models.BooleanField(default=True, help_text="Inactive countries are hidden from rankings and the public site.")
    aliases = models.JSONField(default=list, blank=True, help_text="Alternative names used for automatic country detection.")
    incident_monitoring = models.BooleanField(
        default=False, help_text="BNN has systematic incident monitoring here, so zero verified incidents is a real zero. "
                                 "If off, incident-based indicators are treated as missing (never as zero).")

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "countries"

    def __str__(self):
        return self.name


class ReportingPeriod(TimeStamped):
    """An edition (2026, 2027 …). Only data whose reference/event date falls inside counts towards it."""
    STATUS = [("draft", "Draft"), ("active", "Active – collecting"), ("closed", "Closed"), ("archived", "Archived")]
    name = models.CharField(max_length=60, unique=True)
    slug = models.SlugField(unique=True)
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=10, choices=STATUS, default="draft")
    is_current = models.BooleanField(default=False, help_text="Exactly one period is current; the public site defaults to it.")
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-start_date"]
        constraints = [
            models.CheckConstraint(condition=models.Q(end_date__gte=models.F("start_date")), name="period_end_after_start"),
            models.UniqueConstraint(fields=["is_current"], condition=models.Q(is_current=True), name="one_current_period"),
        ]

    def __str__(self):
        return self.name

    def contains(self, d):
        return d is not None and self.start_date <= d <= self.end_date

    @classmethod
    def current(cls):
        return cls.objects.filter(is_current=True).first()


class AuditLog(models.Model):
    """Append-only record of every create/update/delete on audited models."""
    ACTIONS = [("create", "Create"), ("update", "Update"), ("delete", "Delete"), ("publish", "Publish"),
               ("verify", "Verify"), ("toggle", "Toggle"), ("sync", "Sync")]
    at = models.DateTimeField(auto_now_add=True, db_index=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=10, choices=ACTIONS)
    model = models.CharField(max_length=80, db_index=True)
    object_id = models.CharField(max_length=40, db_index=True)
    object_repr = models.CharField(max_length=255)
    changes = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-at"]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Audit log entries are immutable.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Audit log entries cannot be deleted.")

    def __str__(self):
        return f"{self.at:%Y-%m-%d %H:%M} {self.action} {self.model}#{self.object_id}"
