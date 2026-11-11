"""BNN Asia Index calculation engine.

Rules implemented (see docs/METHODOLOGY.md):
  * Only verified, non-historical observations of the snapshot's reporting period are used.
  * Indicators are min-max normalised to 0–100 (theoretical scale if configured, else observed
    range across Asian countries); lower-is-better indicators are inverted.
  * A category score exists only if ≥ min_category_coverage of its indicator weight has data.
  * Missing data is never zero and can never improve a score: a missing category is imputed with
    the LOWER of (a) the country's own mean across available categories and (b) the regional median
    for that category; the country's coverage and confidence drop accordingly.
  * Countries below min_coverage are "Not Ranked – Insufficient Data".
  * Category switches and the methodology mode decide which categories count.
"""
from __future__ import annotations

import statistics
from collections import defaultdict

from django.db import transaction
from django.utils import timezone

from apps.catalog.models import Indicator, IntelligenceCategory
from apps.core.models import Country
from apps.observations.models import IndicatorObservation

from .models import CountryScore, RankingMethodology, RankingSnapshot


class RankingUnavailable(Exception):
    pass


def effective_weights(methodology: RankingMethodology) -> tuple[dict[int, float], bool, str]:
    """Return ({category_id: weight_fraction}, overall_available, reason)."""
    rows = list(methodology.weights.select_related("category"))
    if not rows:
        return {}, False, "Methodology has no weights."
    active = {w.category_id: w.weight for w in rows if w.category.ranked and w.weight > 0}
    disabled = [w.category.name for w in rows if w.weight > 0 and not w.category.ranked]

    if methodology.mode == "strict" and disabled:
        return {}, False, ("Strict weight mode: overall ranking unavailable because these weighted categories are "
                           "disabled or excluded from ranking: " + ", ".join(disabled))
    if methodology.mode == "custom":
        total = sum(active.values())
        if not 99.5 <= total <= 100.5:
            return {}, False, f"Custom weights of active categories sum to {total:.1f}%, expected 100%."
    total = sum(active.values())
    if total <= 0:
        return {}, False, "No active weighted categories."
    return {cid: w / total for cid, w in active.items()}, True, ""


def _latest_values(indicator: Indicator, period) -> dict[int, IndicatorObservation]:
    qs = (IndicatorObservation.objects
          .filter(indicator=indicator, reporting_period=period, is_historical=False, verification_status="verified",
                  country__is_active=True)
          .order_by("country_id", "-reference_end", "-data_status"))
    out = {}
    for o in qs:
        out.setdefault(o.country_id, o)
    return out


def _normalise(indicator: Indicator, values: dict[int, float], population: dict[int, float]) -> dict[int, float]:
    vals = {}
    for cid, v in values.items():
        if indicator.per_capita:
            pop = population.get(cid)
            if not pop:
                continue  # cannot compute per-capita without population → treated as missing, not zero
            v = v / (pop / 1_000_000)
        vals[cid] = v
    if not vals:
        return {}
    lo = indicator.scale_min if indicator.scale_min is not None else min(vals.values())
    hi = indicator.scale_max if indicator.scale_max is not None else max(vals.values())
    out = {}
    for cid, v in vals.items():
        if hi == lo:
            s = 50.0
        else:
            s = (min(max(v, lo), hi) - lo) / (hi - lo) * 100.0
        if indicator.direction == "lower_better":
            s = 100.0 - s
        out[cid] = round(s, 4)
    return out


def _population(period) -> dict[int, float]:
    ind = Indicator.objects.filter(code="population").first()
    if not ind:
        return {}
    qs = (IndicatorObservation.objects.filter(indicator=ind, verification_status="verified")
          .order_by("country_id", "-reference_end"))
    pop = {}
    for o in qs:
        pop.setdefault(o.country_id, o.value)
    return pop


def calculate(methodology: RankingMethodology, *, note: str = "") -> RankingSnapshot:
    period = methodology.reporting_period
    weights, available, reason = effective_weights(methodology)
    countries = list(Country.objects.filter(is_active=True))
    population = _population(period)

    # 1. Category scores
    cat_scores: dict[int, dict[int, float]] = defaultdict(dict)    # cat -> country -> score
    cat_cov: dict[int, dict[int, float]] = defaultdict(dict)
    details: dict[int, dict] = defaultdict(dict)
    categories = IntelligenceCategory.objects.filter(pk__in=weights.keys()) if weights else \
        IntelligenceCategory.objects.filter(is_enabled=True, scoring_enabled=True)
    for cat in categories:
        inds = list(cat.indicators.filter(is_active=True, used_in_scoring=True))
        total_w = sum(i.weight_in_category for i in inds) or 0
        per_country_sum, per_country_w = defaultdict(float), defaultdict(float)
        for ind in inds:
            latest = _latest_values(ind, period)
            norm = _normalise(ind, {c: o.value for c, o in latest.items()}, population)
            for cid, s in norm.items():
                per_country_sum[cid] += s * ind.weight_in_category
                per_country_w[cid] += ind.weight_in_category
                details[cid].setdefault(cat.slug, {})[ind.code] = {
                    "raw": latest[cid].value, "normalised": s, "ref": latest[cid].reference_label,
                    "status": latest[cid].data_status, "source_url": latest[cid].source_url}
        for c in countries:
            cov = (per_country_w[c.id] / total_w) if total_w else 0.0
            cat_cov[cat.id][c.id] = round(cov, 4)
            if total_w and cov >= methodology.min_category_coverage:
                cat_scores[cat.id][c.id] = round(per_country_sum[c.id] / per_country_w[c.id], 2)

    with transaction.atomic():
        snap = RankingSnapshot.objects.create(
            methodology=methodology, reporting_period=period, calculated_at=timezone.now(),
            effective_weights={str(k): round(v, 6) for k, v in weights.items()},
            overall_available=available, unavailable_reason=reason, notes=note)
        prev = (RankingSnapshot.objects.filter(reporting_period=period, status="published")
                .exclude(pk=snap.pk).order_by("-published_at").first())
        prev_rank = {}
        if prev:
            prev_rank = {(s.country_id, s.category_id): s.rank for s in prev.scores.all()}

        # 2. Per-category ranks
        for cat in categories:
            scored = cat_scores[cat.id]
            ranks = _rank(scored)
            for c in countries:
                CountryScore.objects.create(
                    snapshot=snap, country=c, category=cat, score=scored.get(c.id), rank=ranks.get(c.id),
                    previous_rank=prev_rank.get((c.id, cat.id)), coverage=cat_cov[cat.id].get(c.id, 0.0),
                    is_ranked=c.id in scored, confidence=_confidence(cat_cov[cat.id].get(c.id, 0.0)),
                    status_label="" if c.id in scored else "Not Ranked – Insufficient Data",
                    detail=details[c.id].get(cat.slug, {}))

        # 3. Overall
        overall, cover, imputed = {}, {}, {}
        if available:
            medians = {cid: statistics.median(v.values()) for cid, v in cat_scores.items() if v}
            for c in countries:
                have = {cid: cat_scores[cid][c.id] for cid in weights if c.id in cat_scores[cid]}
                coverage = sum(weights[cid] for cid in have)
                cover[c.id] = round(coverage, 4)
                if coverage < methodology.min_coverage or not have:
                    continue
                own_mean = sum(have.values()) / len(have)
                total, imp = 0.0, []
                for cid, w in weights.items():
                    if cid in have:
                        total += have[cid] * w
                    else:
                        fill = min(own_mean, medians.get(cid, own_mean))
                        total += fill * w
                        imp.append(cid)
                overall[c.id] = round(total, 2)
                imputed[c.id] = imp
        ranks = _rank(overall)
        for c in countries:
            ranked = c.id in overall
            label = ("" if ranked else
                     ("Ranking unavailable – " + reason) if not available else "Not Ranked – Insufficient Data")
            CountryScore.objects.create(
                snapshot=snap, country=c, category=None, score=overall.get(c.id), rank=ranks.get(c.id),
                previous_rank=prev_rank.get((c.id, None)), coverage=cover.get(c.id, 0.0), is_ranked=ranked,
                confidence=_confidence(cover.get(c.id, 0.0), imputed=bool(imputed.get(c.id))),
                status_label=label[:60], imputed_categories=imputed.get(c.id, []))
    return snap


def _rank(scores: dict[int, float]) -> dict[int, int]:
    """Standard competition ranking (1, 2, 2, 4)."""
    ordered = sorted(scores.items(), key=lambda kv: -kv[1])
    ranks, last, last_rank = {}, None, 0
    for i, (cid, s) in enumerate(ordered, start=1):
        if s != last:
            last_rank, last = i, s
        ranks[cid] = last_rank
    return ranks


def _confidence(coverage: float, imputed: bool = False) -> str:
    if coverage >= 0.9 and not imputed:
        return "high"
    if coverage >= 0.75:
        return "medium"
    return "low"


@transaction.atomic
def publish(snapshot: RankingSnapshot):
    if snapshot.status != "draft":
        raise ValueError("Only draft snapshots can be published.")
    RankingSnapshot.objects.filter(reporting_period=snapshot.reporting_period, status="published",
                                   methodology__name=snapshot.methodology.name).update(status="superseded")
    m = snapshot.methodology
    if not m.is_published:
        RankingMethodology.objects.filter(pk=m.pk).update(is_published=True, published_at=timezone.now())
    snapshot.status = "published"
    snapshot.published_at = timezone.now()
    snapshot.save(update_fields=["status", "published_at", "updated_at"])
    return snapshot
