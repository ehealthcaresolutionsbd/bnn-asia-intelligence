"""Turns verified incidents into indicator observations (Stage C output → scoring input)."""
from django.db.models import Count
from django.utils import timezone

from apps.catalog.models import Indicator
from apps.core.models import Country
from apps.observations.models import IndicatorObservation
from apps.sources.models import DataSource

from .models import Incident


def aggregate_incidents(period, mapping):
    src = DataSource.objects.get(slug="bnn-incidents")
    created = 0
    for code, type_slugs in mapping.items():
        ind = Indicator.objects.filter(code=code).first()
        if not ind:
            continue
        counts = dict(Incident.objects.filter(
            reporting_period=period, verification_status="verified", duplicate_of__isnull=True,
            incident_type__slug__in=type_slugs, event_date__gte=period.start_date, event_date__lte=period.end_date)
            .values_list("country_id").annotate(n=Count("id")))
        for c in Country.objects.filter(is_active=True):
            n = counts.get(c.id)
            if n is None and not c.incident_monitoring:
                # No monitoring → no observation. Missing stays missing (never zero).
                IndicatorObservation.objects.filter(indicator=ind, country=c, reporting_period=period, source=src).delete()
                continue
            IndicatorObservation.objects.update_or_create(
                indicator=ind, country=c, reporting_period=period, reference_label=f"BNN {period.name}", source=src,
                defaults=dict(value=float(n or 0), reference_start=period.start_date, reference_end=min(period.end_date, timezone.now().date()),
                              source_url=f"https://bnnasia.org/country/{c.slug}/", collected_at=timezone.now(),
                              verification_status="verified", verified_at=timezone.now(), data_status="preliminary",
                              notes="Aggregated from BNN verified incident records (year to date)."))
            created += 1
    return created
