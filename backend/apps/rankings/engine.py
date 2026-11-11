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
  * Indicators with transform="log" are normalised on log(1 + x) (skewed event rates).
  * Uncertainty (methodology v2): observations carrying a 90% interval (ci_low/ci_high) are redrawn MC_DRAWS times
    from N(value, sd = (ci_high − ci_low) / 3.29) (3.29 = 2 × 1.645 for a 90% normal interval); the whole category and
    overall calculation is repeated per draw (vectorised with numpy) and the 5th–95th percentiles of score and rank are
    stored in CountryScore.detail as score_ci and rank_interval [best, worst].
  * Editorial adjustments (apps.signals.EditorialAdjustment) of the period: "override" replaces a computed category or
    overall score before ranking, "exclude" removes the country from that ranking ("Excluded by editors"), "note" only
    annotates. Every adjustment is stored in detail["editorial"] with its reason and the original computed score.
"""
from __future__ import annotations

import math
import statistics
import warnings
from collections import defaultdict

import numpy as np

from django.db import transaction
from django.utils import timezone

from apps.catalog.models import Indicator, IntelligenceCategory
from apps.core.models import Country
from apps.observations.models import IndicatorObservation

from .models import CountryScore, RankingMethodology, RankingSnapshot


MC_DRAWS = 300
MC_SEED = 20260
Z90 = 3.29   # width of a 90 % normal interval in standard deviations (2 × 1.645)


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
    log = getattr(indicator, "transform", "none") == "log"
    if log:
        vals = {cid: math.log1p(max(v, 0.0)) for cid, v in vals.items()}
    lo = _scale(indicator.scale_min, log) if indicator.scale_min is not None else min(vals.values())
    hi = _scale(indicator.scale_max, log) if indicator.scale_max is not None else max(vals.values())
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


def _scale(x, log):
    return math.log1p(max(x, 0.0)) if log else x


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


def _adjustments(period):
    from apps.signals.models import EditorialAdjustment
    out = defaultdict(list)
    for a in EditorialAdjustment.objects.filter(reporting_period=period, is_active=True).order_by("created_at", "pk"):
        out[(a.country_id, a.category_id)].append(a)
    return out


def _apply_editorial(adjs, scores: dict[int, float], cat_id, log, excluded: set):
    """Apply override/exclude/note adjustments for one ranking (cat_id None = overall) in place."""
    for (cid, acat), items in adjs.items():
        if acat != cat_id:
            continue
        for a in items:
            original = scores.get(cid)
            if a.kind == "override" and a.score is not None:
                scores[cid] = round(min(max(a.score, 0.0), 100.0), 2)
            elif a.kind == "exclude":
                excluded.add(cid)
            log[cid].append({"kind": a.kind, "reason": a.reason, "original_score": original,
                             **({"score": a.score} if a.kind == "override" else {})})


def _overall_scores(cat_scores, weights, countries, min_coverage):
    overall, cover, imputed = {}, {}, {}
    medians = {cid: statistics.median(v.values()) for cid, v in cat_scores.items() if v}
    for c in countries:
        have = {cid: cat_scores[cid][c.id] for cid in weights if c.id in cat_scores[cid]}
        coverage = sum(weights[cid] for cid in have)
        cover[c.id] = round(coverage, 4)
        if coverage < min_coverage or not have:
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
    return overall, cover, imputed


def calculate(methodology: RankingMethodology, *, note: str = "", mc_draws: int = MC_DRAWS,
              seed: int = MC_SEED) -> RankingSnapshot:
    period = methodology.reporting_period
    weights, available, reason = effective_weights(methodology)
    countries = list(Country.objects.filter(is_active=True))
    population = _population(period)
    adjs = _adjustments(period)

    # 1. Category scores
    cat_scores: dict[int, dict[int, float]] = defaultdict(dict)    # cat -> country -> score
    cat_cov: dict[int, dict[int, float]] = defaultdict(dict)
    details: dict[int, dict] = defaultdict(dict)
    inputs: dict[int, list] = {}                                    # cat -> [(indicator, {cid: obs})] for Monte Carlo
    categories = list(IntelligenceCategory.objects.filter(pk__in=weights.keys()) if weights else
                      IntelligenceCategory.objects.filter(is_enabled=True, scoring_enabled=True))
    for cat in categories:
        inds = list(cat.indicators.filter(is_active=True, used_in_scoring=True))
        total_w = sum(i.weight_in_category for i in inds) or 0
        per_country_sum, per_country_w = defaultdict(float), defaultdict(float)
        inputs[cat.id] = []
        for ind in inds:
            latest = _latest_values(ind, period)
            inputs[cat.id].append((ind, latest))
            norm = _normalise(ind, {c: o.value for c, o in latest.items()}, population)
            for cid, s in norm.items():
                per_country_sum[cid] += s * ind.weight_in_category
                per_country_w[cid] += ind.weight_in_category
                o = latest[cid]
                d = {"raw": o.value, "normalised": s, "ref": o.reference_label, "status": o.data_status,
                     "source_url": o.source_url}
                if o.ci_low is not None and o.ci_high is not None:
                    d.update(ci=[o.ci_low, o.ci_high], sample_size=o.sample_size)
                details[cid].setdefault(cat.slug, {})[ind.code] = d
        for c in countries:
            cov = (per_country_w[c.id] / total_w) if total_w else 0.0
            cat_cov[cat.id][c.id] = round(cov, 4)
            if total_w and cov >= methodology.min_category_coverage:
                cat_scores[cat.id][c.id] = round(per_country_sum[c.id] / per_country_w[c.id], 2)

    # 1b. Editorial adjustments on categories (before ranking and before the overall score uses them)
    editorial: dict = defaultdict(lambda: defaultdict(list))        # cat_id|None -> cid -> entries
    excluded: dict = defaultdict(set)
    for cat in categories:
        _apply_editorial(adjs, cat_scores[cat.id], cat.id, editorial[cat.id], excluded[cat.id])

    # 2. Overall (+ editorial)
    overall, cover, imputed = ({}, {}, {})
    if available:
        overall, cover, imputed = _overall_scores(cat_scores, weights, countries, methodology.min_coverage)
        _apply_editorial(adjs, overall, None, editorial[None], excluded[None])

    # 3. Uncertainty: Monte Carlo score intervals and rank intervals
    mc = _monte_carlo(methodology, categories, inputs, countries, population, weights, available, cat_scores,
                      overall, excluded, adjs, draws=mc_draws, seed=seed) if mc_draws else {}

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

        rows = []
        # 4. Per-category ranks
        for cat in categories:
            scored = cat_scores[cat.id]
            ex = excluded[cat.id]
            ranks = _rank({k: v for k, v in scored.items() if k not in ex})
            for c in countries:
                is_ex = c.id in ex
                ranked = c.id in scored and not is_ex
                detail = dict(details[c.id].get(cat.slug, {}))
                detail.update(_mc_detail(mc, c.id, cat.id, scored.get(c.id), ranks.get(c.id)))
                detail["editorial"] = editorial[cat.id].get(c.id, [])
                rows.append(CountryScore(
                    snapshot=snap, country=c, category=cat, score=None if is_ex else scored.get(c.id),
                    rank=ranks.get(c.id), previous_rank=prev_rank.get((c.id, cat.id)),
                    coverage=cat_cov[cat.id].get(c.id, 0.0), is_ranked=ranked,
                    confidence=_confidence(cat_cov[cat.id].get(c.id, 0.0)),
                    status_label="" if ranked else ("Excluded by editors" if is_ex else "Not Ranked – Insufficient Data"),
                    detail=detail))

        # 5. Overall
        ex = excluded[None]
        ranks = _rank({k: v for k, v in overall.items() if k not in ex})
        for c in countries:
            is_ex = c.id in ex
            ranked = c.id in overall and not is_ex
            if ranked:
                label = ""
            elif is_ex:
                label = "Excluded by editors"
            elif not available:
                label = "Ranking unavailable – " + reason
            else:
                label = "Not Ranked – Insufficient Data"
            detail = _mc_detail(mc, c.id, None, overall.get(c.id), ranks.get(c.id))
            detail["editorial"] = editorial[None].get(c.id, [])
            rows.append(CountryScore(
                snapshot=snap, country=c, category=None, score=None if is_ex else overall.get(c.id),
                rank=ranks.get(c.id), previous_rank=prev_rank.get((c.id, None)), coverage=cover.get(c.id, 0.0),
                is_ranked=ranked, confidence=_confidence(cover.get(c.id, 0.0), imputed=bool(imputed.get(c.id))),
                status_label=label[:60], imputed_categories=imputed.get(c.id, []), detail=detail))
        CountryScore.objects.bulk_create(rows)
    return snap


def _mc_detail(mc, cid, cat_id, score, rank):
    """score_ci / rank_interval for one row, widened to contain the point estimate."""
    r = mc.get((cid, cat_id))
    out = {"score_ci": None, "rank_interval": None}
    if score is None or r is None:
        return out
    lo, hi = r["score"]
    out["score_ci"] = [round(min(lo, score), 2), round(max(hi, score), 2)]
    if rank is not None and r.get("rank") is not None:
        best, worst = r["rank"]
        out["rank_interval"] = [int(min(best, rank)), int(max(worst, rank))]
    return out


def _mc_rank(s: np.ndarray) -> np.ndarray:
    """Competition rank per draw. s: (N, C) scores, NaN = not ranked → rank NaN."""
    valid = ~np.isnan(s)
    filled = np.where(valid, s, -np.inf)
    higher = (filled[:, None, :] > filled[:, :, None]).sum(axis=2)
    return np.where(valid, higher + 1, np.nan)


def _monte_carlo(methodology, categories, inputs, countries, population, weights, available, cat_point,
                 overall_point, excluded, adjs, *, draws, seed):
    """Vectorised re-run of the category + overall calculation under observation uncertainty.

    Returns {(country_id, category_id|None): {"score": (p5, p95), "rank": (best, worst)}}.
    """
    rng = np.random.default_rng(seed)
    idx = {c.id: i for i, c in enumerate(countries)}
    n, nc = draws, len(countries)
    out = {}
    cat_draw: dict[int, np.ndarray] = {}
    for cat in categories:
        items = inputs.get(cat.id, [])
        total_w = sum(ind.weight_in_category for ind, _ in items)
        s_sum = np.zeros((n, nc))
        w_sum = np.zeros(nc)
        for ind, latest in items:
            base = np.full(nc, np.nan)
            sd = np.zeros(nc)
            for cid, o in latest.items():
                if cid not in idx:
                    continue
                v = o.value
                if ind.per_capita:
                    pop = population.get(cid)
                    if not pop:
                        continue
                    factor = 1.0 / (pop / 1_000_000)
                else:
                    factor = 1.0
                base[idx[cid]] = v * factor
                if o.ci_low is not None and o.ci_high is not None and o.ci_high > o.ci_low:
                    sd[idx[cid]] = (o.ci_high - o.ci_low) / Z90 * factor
            have = ~np.isnan(base)
            if not have.any():
                continue
            x = base[None, :] + sd[None, :] * rng.standard_normal((n, nc))
            x = np.where(base[None, :] >= 0, np.maximum(x, 0.0), x)       # non-negative quantities stay ≥ 0
            log = getattr(ind, "transform", "none") == "log"
            if log:
                x = np.log1p(np.maximum(x, 0.0))
            with np.errstate(all="ignore"):
                lo = np.full((n, 1), _scale(ind.scale_min, log)) if ind.scale_min is not None else \
                    np.nanmin(x, axis=1, keepdims=True)
                hi = np.full((n, 1), _scale(ind.scale_max, log)) if ind.scale_max is not None else \
                    np.nanmax(x, axis=1, keepdims=True)
                rng_ = hi - lo
                s = np.where(rng_ == 0, 50.0, (np.clip(x, lo, hi) - lo) / np.where(rng_ == 0, 1, rng_) * 100.0)
            if ind.direction == "lower_better":
                s = 100.0 - s
            s_sum += np.where(have[None, :], s, 0.0) * ind.weight_in_category
            w_sum += have * ind.weight_in_category
        cov = (w_sum / total_w) if total_w else np.zeros(nc)
        ok = (cov >= methodology.min_category_coverage) & (w_sum > 0) if total_w else np.zeros(nc, bool)
        with np.errstate(all="ignore"):
            sc = np.where(ok[None, :], s_sum / np.where(w_sum > 0, w_sum, 1)[None, :], np.nan)
        # editorial overrides are fixed values in every draw
        for (cid, acat), items_ in adjs.items():
            if acat == cat.id and cid in idx:
                for a in items_:
                    if a.kind == "override" and a.score is not None:
                        sc[:, idx[cid]] = min(max(a.score, 0.0), 100.0)
        cat_draw[cat.id] = sc
        ranked = sc.copy()
        for cid in excluded.get(cat.id, ()):
            if cid in idx:
                ranked[:, idx[cid]] = np.nan
        _collect(out, countries, cat.id, sc, _mc_rank(np.round(ranked, 2)))

    if available and weights:
        cids = [k for k in weights if k in cat_draw]
        if cids:
            stack = np.stack([cat_draw[k] for k in cids])            # (K, N, C)
            w = np.array([weights[k] for k in cids])[:, None, None]
            have = ~np.isnan(stack[:, 0, :])                          # missingness is fixed across draws (K, C)
            coverage = (have * w[:, :, 0]).sum(axis=0)
            with warnings.catch_warnings(), np.errstate(all="ignore"):
                warnings.simplefilter("ignore", RuntimeWarning)
                own_mean = np.nanmean(stack, axis=0)                  # (N, C)
                med = np.nanmedian(stack, axis=2)                     # (K, N)
            med = np.where(np.isnan(med)[:, :, None], own_mean[None, :, :], med[:, :, None])
            fill = np.minimum(own_mean[None, :, :], med)
            total = (np.where(np.isnan(stack), fill, stack) * w).sum(axis=0)
            okc = (coverage >= methodology.min_coverage) & have.any(axis=0)
            ov = np.where(okc[None, :], total, np.nan)
            for (cid, acat), items_ in adjs.items():
                if acat is None and cid in idx:
                    for a in items_:
                        if a.kind == "override" and a.score is not None:
                            ov[:, idx[cid]] = min(max(a.score, 0.0), 100.0)
            ranked = ov.copy()
            for cid in excluded.get(None, ()):
                if cid in idx:
                    ranked[:, idx[cid]] = np.nan
            _collect(out, countries, None, ov, _mc_rank(np.round(ranked, 2)))
    return out


def _collect(out, countries, cat_id, scores, ranks):
    with warnings.catch_warnings(), np.errstate(all="ignore"):
        warnings.simplefilter("ignore", RuntimeWarning)
        s_lo, s_hi = np.nanpercentile(scores, [5, 95], axis=0) if np.isfinite(scores).any() else (None, None)
        r_lo, r_hi = np.nanpercentile(ranks, [5, 95], axis=0) if np.isfinite(ranks).any() else (None, None)
    if s_lo is None:
        return
    for i, c in enumerate(countries):
        if np.isnan(s_lo[i]):
            continue
        rank = None
        if r_lo is not None and not np.isnan(r_lo[i]):
            rank = (math.floor(r_lo[i]), math.ceil(r_hi[i]))
        out[(c.id, cat_id)] = {"score": (float(s_lo[i]), float(s_hi[i])), "rank": rank}


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
