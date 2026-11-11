from celery import shared_task

from apps.core.models import ReportingPeriod


@shared_task
def refresh_index_task(period_slug: str | None = None):
    from .pipeline import refresh_annual_index
    period = ReportingPeriod.objects.get(slug=period_slug) if period_slug else ReportingPeriod.current()
    return refresh_annual_index(period)
