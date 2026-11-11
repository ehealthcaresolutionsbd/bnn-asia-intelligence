import os

from django.utils import timezone

from apps.core.models import AuditLog, ReportingPeriod

from .connectors import get_connector
from .models import DataCollectionLog, DataSource


def test_source(source: DataSource):
    """Run the connector's self-test and record the outcome in the integration registry."""
    source.last_test_at = timezone.now()
    if source.requires_credentials and not os.environ.get(source.credentials_env_var or "_none_"):
        source.status, source.last_test_message = "needs_auth", f"Set {source.credentials_env_var} to enable."
        source.save()
        return False
    if not source.connector:
        source.status, source.last_test_message = "configured", "Internal source – filled by aggregate_incidents."
        source.save()
        return True
    conn = get_connector(source)
    if not conn:
        source.status, source.last_test_message = "discovered", "No connector implemented."
        source.save()
        return False
    try:
        ok, msg = conn.test()
    except Exception as e:  # network/HTTP/parse errors are recorded, not raised
        ok, msg = False, f"{type(e).__name__}: {e}"[:500]
    if source.connector == "manual":
        source.status = "configured" if "HTTP 200" in msg else "failing"
    elif source.status == "restricted":
        pass  # stays restricted until terms are confirmed, even if technically reachable
    else:
        source.status = "tested_ok" if ok else "failing"
    source.last_test_message = msg
    source.save()
    return ok


def sync_source(source: DataSource, period=None, triggered_by="manual"):
    period = period or ReportingPeriod.current()
    log = DataCollectionLog.objects.create(source=source, triggered_by=triggered_by)
    conn = get_connector(source)
    try:
        if not conn:
            raise RuntimeError("No connector")
        if not source.is_active or source.status in ("restricted", "needs_auth", "disabled"):
            raise RuntimeError(f"Source not runnable (status={source.status}, active={source.is_active})")
        res = conn.run(period)
        log.status, log.items_fetched, log.items_created, log.items_skipped = res.status, res.fetched, res.created, res.skipped
        log.message = "; ".join(res.messages)[:2000]
        if res.status != "failed":
            source.last_success_at = timezone.now()
    except Exception as e:
        log.status, log.message = "failed", f"{type(e).__name__}: {e}"[:2000]
    log.finished_at = timezone.now()
    log.save()
    source.last_sync_at = timezone.now()
    source.save(update_fields=["last_sync_at", "last_success_at", "updated_at"])
    AuditLog.objects.create(action="sync", model="sources.DataSource", object_id=str(source.pk),
                            object_repr=source.name, changes={"status": log.status, "created": log.items_created})
    return log
