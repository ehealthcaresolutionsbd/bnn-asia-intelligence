from datetime import datetime, timedelta, timezone

from celery import shared_task

from .ingest import ingest_day


@shared_task
def ingest_yesterday():
    """Ingest the GDELT export of the previous UTC day (published by GDELT shortly after midnight UTC)."""
    day = datetime.now(timezone.utc).date() - timedelta(days=1)
    r = ingest_day(day)
    return {"day": day.isoformat(), "status": r.status, "seconds": round(r.seconds, 1), "message": r.message[:500]}
