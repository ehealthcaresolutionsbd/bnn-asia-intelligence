from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from .models import DataSource
from .services import sync_source


@shared_task
def sync_due_sources():
    now = timezone.now()
    done = []
    for s in DataSource.objects.filter(is_active=True, status="tested_ok").exclude(connector__in=["", "manual"]):
        if s.last_sync_at and s.last_sync_at > now - timedelta(hours=s.sync_interval_hours):
            continue
        cats = list(s.indicators.values_list("category__is_enabled", "category__collection_enabled"))
        if cats and not any(a and b for a, b in cats):
            continue  # every category fed by this source has collection switched off
        done.append((s.slug, sync_source(s, triggered_by="schedule").status))
    return done
