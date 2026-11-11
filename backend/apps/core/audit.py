"""Automatic audit logging for models listed in AUDITED_MODELS."""
import threading

from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver
from django.forms.models import model_to_dict

_local = threading.local()


def set_current_user(user):
    _local.user = user if (user and user.is_authenticated) else None


def get_current_user():
    return getattr(_local, "user", None)


AUDITED_MODELS = {
    "catalog.IntelligenceCategory", "catalog.Indicator", "core.ReportingPeriod", "core.Country",
    "sources.DataSource", "observations.IndicatorObservation", "incidents.Incident", "incidents.IncidentClaim",
    "incidents.IncidentEvidence", "rankings.RankingMethodology", "rankings.MethodologyWeight",
    "rankings.RankingSnapshot", "reports.CountryReport",
}


def _label(sender):
    return f"{sender._meta.app_label}.{sender.__name__}"


def _jsonable(d):
    out = {}
    for k, v in d.items():
        out[k] = v if isinstance(v, (str, int, float, bool, type(None), list, dict)) else str(v)
    return out


@receiver(pre_save)
def _capture_old(sender, instance, **kwargs):
    if _label(sender) in AUDITED_MODELS and instance.pk:
        old = sender.objects.filter(pk=instance.pk).first()
        instance._audit_old = _jsonable(model_to_dict(old)) if old else None


@receiver(post_save)
def _log_save(sender, instance, created, **kwargs):
    if _label(sender) not in AUDITED_MODELS:
        return
    from .models import AuditLog
    new = _jsonable(model_to_dict(instance))
    if created:
        changes = new
    else:
        old = getattr(instance, "_audit_old", None) or {}
        changes = {k: [old.get(k), v] for k, v in new.items() if old.get(k) != v}
        if not changes:
            return
    AuditLog.objects.create(user=get_current_user(), action="create" if created else "update",
                            model=_label(sender), object_id=str(instance.pk), object_repr=str(instance)[:255],
                            changes=changes)


@receiver(post_delete)
def _log_delete(sender, instance, **kwargs):
    if _label(sender) not in AUDITED_MODELS:
        return
    from .models import AuditLog
    AuditLog.objects.create(user=get_current_user(), action="delete", model=_label(sender),
                            object_id=str(instance.pk), object_repr=str(instance)[:255])
