"""Weekly auto-refresh of BNN Asia's own annual index (methodology v2)."""
from __future__ import annotations

import logging

from apps.core.models import ReportingPeriod
from apps.rankings.engine import calculate, publish
from apps.rankings.models import RankingMethodology

from .indicators import build_signal_indicators

log = logging.getLogger(__name__)
V2 = ("BNN Asia Index", "2.0.0")


def v2_methodology(period) -> RankingMethodology:
    return RankingMethodology.objects.get(name=V2[0], version=V2[1], reporting_period=period)


def refresh_annual_index(period: ReportingPeriod | None = None, *, publish_result: bool = True) -> dict:
    """signals → BNN indicators → incident indicators → calculate(v2) → publish.

    A published (frozen) v2 methodology is reused: every refresh creates a new snapshot under it and the previous
    published snapshot of the period becomes "superseded" (kept for ranking history).
    """
    from apps.core.management.commands.seed_platform import INCIDENT_INDICATOR_MAP
    from apps.incidents.services import aggregate_incidents

    period = period or ReportingPeriod.current()
    if period is None:
        raise ValueError("No current reporting period.")
    m = v2_methodology(period)
    sig = build_signal_indicators(period)
    inc = aggregate_incidents(period, INCIDENT_INDICATOR_MAP)
    snap = calculate(m, note=f"Automatic weekly refresh (signals: {sig['written']} observations to "
                             f"{sig['reference_end']}; incidents: {inc} observations)")
    if publish_result:
        publish(snap)
    ranked = snap.scores.filter(category=None, is_ranked=True).count()
    out = {"period": period.slug, "snapshot": snap.pk, "status": snap.status, "ranked": ranked,
           "signal_observations": sig["written"], "signal_missing": sig["missing"],
           "reference_end": str(sig["reference_end"]), "incident_observations": inc}
    log.info("BNN index refresh: %s", out)
    return out
