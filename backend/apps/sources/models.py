from django.db import models

from apps.core.models import TimeStamped


class DataSource(TimeStamped):
    """Registry of every organisation / feed / dataset the platform draws on.

    This is also the integration registry: each row records how it is collected,
    whether credentials are needed, and the result of the last automated test.
    """
    KIND = [("original", "Original data provider"), ("secondary", "Secondary reporting"), ("news", "News outlet"),
            ("official_stats", "National statistics / central bank")]
    METHOD = [("api", "Official API"), ("dataset", "Downloadable dataset"), ("rss", "RSS feed"),
              ("manual", "Manual entry / researcher import"), ("scrape_permitted", "Permitted extraction")]
    STATUS = [("discovered", "Discovered"), ("configured", "Configured"), ("tested_ok", "Tested – working"),
              ("needs_auth", "Requires authorisation / API key"), ("restricted", "Restricted – terms do not allow automation"),
              ("failing", "Failing"), ("disabled", "Disabled")]

    name = models.CharField(max_length=200, unique=True)
    slug = models.SlugField(max_length=120, unique=True)
    organisation = models.CharField(max_length=200)
    website = models.URLField()
    kind = models.CharField(max_length=16, choices=KIND)
    method = models.CharField(max_length=20, choices=METHOD)
    endpoint = models.URLField(blank=True, max_length=500)
    connector = models.CharField(max_length=60, blank=True, help_text="Python connector key in apps.sources.connectors.REGISTRY")
    config = models.JSONField(default=dict, blank=True)
    licence = models.CharField(max_length=200, blank=True)
    terms_notes = models.TextField(blank=True, help_text="What the terms of service allow (attribution, republication, automation).")
    reliability = models.PositiveSmallIntegerField(default=3, help_text="1 (low) – 5 (high) editorial reliability rating.")
    methodology_url = models.URLField(blank=True)
    requires_credentials = models.BooleanField(default=False)
    credentials_env_var = models.CharField(max_length=80, blank=True, help_text="Name of the env var that holds the key. Never store keys here.")
    status = models.CharField(max_length=12, choices=STATUS, default="discovered")
    is_active = models.BooleanField(default=True)
    sync_interval_hours = models.PositiveIntegerField(default=24)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    last_success_at = models.DateTimeField(null=True, blank=True)
    last_test_at = models.DateTimeField(null=True, blank=True)
    last_test_message = models.TextField(blank=True)
    alternative = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL,
                                    help_text="Fallback provider if this one is unavailable.")

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class SourceDataset(TimeStamped):
    """A specific dataset/edition from a source, e.g. 'CPI 2025' or 'WDI GDP per capita'."""
    source = models.ForeignKey(DataSource, on_delete=models.PROTECT, related_name="datasets")
    name = models.CharField(max_length=200)
    edition = models.CharField(max_length=40, blank=True)
    url = models.URLField(max_length=500, blank=True)
    published_at = models.DateField(null=True, blank=True)
    retrieved_at = models.DateTimeField(null=True, blank=True)
    checksum = models.CharField(max_length=64, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        unique_together = [("source", "name", "edition")]
        ordering = ["source", "-published_at"]

    def __str__(self):
        return f"{self.source.name} – {self.name} {self.edition}".strip()


class DataCollectionLog(models.Model):
    STATUS = [("running", "Running"), ("success", "Success"), ("partial", "Partial"), ("failed", "Failed")]
    source = models.ForeignKey(DataSource, on_delete=models.CASCADE, related_name="logs")
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=8, choices=STATUS, default="running")
    items_fetched = models.PositiveIntegerField(default=0)
    items_created = models.PositiveIntegerField(default=0)
    items_skipped = models.PositiveIntegerField(default=0)
    message = models.TextField(blank=True)
    triggered_by = models.CharField(max_length=40, default="schedule")

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"{self.source} @ {self.started_at:%Y-%m-%d %H:%M} – {self.status}"
