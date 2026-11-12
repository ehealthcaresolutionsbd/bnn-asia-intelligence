"""BNN Asia's own statistics: GDELT signal aggregates → IndicatorObservation rows.

Formulas (period-to-date, reference period = period start … last ingested day):

    rate per 1,000      r = 1000 · Σ signal events / Σ all in-country events          (CountryVolumeDaily)
    protest repression  p = 100 · Σ protest_repression / (Σ protests + Σ protest_repression)

Why rates and not counts: GDELT records what the media report. India, China or Israel generate tens of thousands of
events a month, the Maldives or Turkmenistan a few hundred. Raw counts would mostly measure media attention. Dividing by
*all* events located in the same country and period ("coverage correction") turns the count into the share of that
country's reported events that are repression/censorship/violence, which is comparable between countries with very
different coverage. Protest repression uses protest-related events as its own denominator.

Countries with fewer than MIN_EVENTS in-country events in the period get NO observation (missing, never zero): the rate
would be too noisy to rank.

Uncertainty: block bootstrap by ISO week. Days within a week are strongly correlated (one story produces many events
over several days), so whole weeks are resampled with replacement (B = 1,000, RNG seeded per indicator/country/period
for reproducibility) and the ratio is recomputed on each resample; the 5th–95th percentiles form the 90% interval.
The interval is widened, if necessary, to contain the point estimate (percentile intervals of a ratio estimator can
exclude it in very small samples).
"""
from __future__ import annotations

import datetime as dt
import zlib
from collections import defaultdict

import numpy as np
from django.db import transaction
from django.db.models import Max, Sum
from django.utils import timezone

from apps.catalog.models import Indicator
from apps.core.models import Country
from apps.observations.models import IndicatorObservation
from apps.sources.models import DataSource

from .models import CountryVolumeDaily, IngestedDay, SignalDaily

MIN_EVENTS = 300
MIN_SHARE_EVENTS = 30   # a share (e.g. protest repression %) needs at least 30 events in its denominator
MIN_WEEKS = 4          # at least 4 ISO weeks with data before a value (and its interval) is published
BOOTSTRAP_B = 1000
CI_LEVEL = 0.90
METHOD_VERSION = "v2"
SOURCE_SLUG = "bnn-signals"

# indicator code → (numerator signals, denominator spec, multiplier)
# denominator "volume" = all in-country events; a tuple = sum of those signals.
SIGNAL_INDICATORS = {
    "bnn_sig_media_repression": (("media_repression",), "volume", 1000.0),
    "bnn_sig_censorship": (("censorship",), "volume", 1000.0),
    "bnn_sig_state_repression": (("state_repression",), "volume", 1000.0),
    "bnn_sig_arrests": (("arrests_detentions",), "volume", 1000.0),
    "bnn_sig_violence": (("killings_assaults",), "volume", 1000.0),
    "bnn_sig_protest_repression": (("protest_repression",), ("protests", "protest_repression"), 100.0),
}


def last_ingested_day(period) -> dt.date | None:
    """Last day with data inside the period (successful IngestedDay, else the latest aggregate row)."""
    qs = IngestedDay.objects.filter(status="ok", day__gte=period.start_date, day__lte=period.end_date)
    d = qs.aggregate(m=Max("day"))["m"]
    if d is None:
        d = CountryVolumeDaily.objects.filter(day__gte=period.start_date, day__lte=period.end_date).aggregate(m=Max("day"))["m"]
    return d


def _week_index(days: list[dt.date]) -> dict[dt.date, int]:
    keys = sorted({d.isocalendar()[:2] for d in days})
    pos = {k: i for i, k in enumerate(keys)}
    return {d: pos[d.isocalendar()[:2]] for d in days}


def bootstrap_ratio_ci(num_weeks, den_weeks, multiplier: float, *, seed: int, b: int = BOOTSTRAP_B,
                       level: float = CI_LEVEL) -> tuple[float, float]:
    """Percentile CI of multiplier·Σnum/Σden under resampling of weeks with replacement."""
    num = np.asarray(num_weeks, dtype=float)
    den = np.asarray(den_weeks, dtype=float)
    w = len(num)
    point = multiplier * num.sum() / den.sum()
    if w < 2:
        return point, point
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, w, size=(b, w))
    n_b, d_b = num[idx].sum(axis=1), den[idx].sum(axis=1)
    ok = d_b > 0
    r = multiplier * n_b[ok] / d_b[ok]
    if not len(r):
        return point, point
    a = (1 - level) / 2 * 100
    lo, hi = np.percentile(r, [a, 100 - a])
    return float(min(lo, point)), float(max(hi, point))


def _seed(code: str, iso3: str, period_slug: str) -> int:
    return zlib.crc32(f"{code}:{iso3}:{period_slug}:{METHOD_VERSION}".encode())


def build_signal_indicators(period, *, today: dt.date | None = None) -> dict:
    """Compute BNN signal indicators for every active country; returns a summary dict."""
    today = today or timezone.now().date()
    src, _ = DataSource.objects.get_or_create(slug=SOURCE_SLUG, defaults=dict(
        name="BNN Asia – event data analysis (GDELT)", organisation="BNN Asia", website="https://bnnasia.org",
        kind="original", method="dataset", status="configured", reliability=4,
        terms_notes="Internal: statistics computed by BNN Asia from GDELT 2.0 event data."))
    indicators = {i.code: i for i in Indicator.objects.filter(code__in=SIGNAL_INDICATORS)}
    end = last_ingested_day(period)
    summary = {"period": period.slug, "reference_end": end, "written": 0, "missing": 0, "countries": 0}
    if end is None or not indicators:
        return summary
    start = period.start_date
    label = f"BNN signals {period.name}"[:40]
    status = "final" if end >= period.end_date else "preliminary"   # final only once 31 Dec is ingested

    # Daily volume and signals → per-country, per-day dicts.
    vol = defaultdict(dict)          # cid -> day -> (events, articles)
    for cid, day, ev, art in CountryVolumeDaily.objects.filter(day__gte=start, day__lte=end).values_list(
            "country_id", "day", "events", "articles"):
        vol[cid][day] = (ev, art)
    sig = defaultdict(lambda: defaultdict(dict))   # cid -> signal -> day -> (events, articles)
    for cid, day, key, ev, art in SignalDaily.objects.filter(day__gte=start, day__lte=end).values_list(
            "country_id", "day", "signal", "events", "articles"):
        sig[cid][key][day] = (ev, art)

    all_days = [start + dt.timedelta(days=i) for i in range((end - start).days + 1)]
    week_of = _week_index(all_days)
    n_weeks = max(week_of.values()) + 1

    def weekly(daymap) -> np.ndarray:
        out = np.zeros(n_weeks)
        for d, (ev, _) in daymap.items():
            out[week_of[d]] += ev
        return out

    def articles(daymap) -> int:
        return int(sum(a for _, a in daymap.values()))

    now = timezone.now()
    with transaction.atomic():
        for c in Country.objects.filter(is_active=True):
            summary["countries"] += 1
            v_week = weekly(vol.get(c.id, {}))
            total_events = int(v_week.sum())
            for code, (nums, den_spec, mult) in SIGNAL_INDICATORS.items():
                ind = indicators.get(code)
                if not ind:
                    continue
                num_w = sum((weekly(sig[c.id][k]) for k in nums), np.zeros(n_weeks))
                num_art = sum(articles(sig[c.id][k]) for k in nums)
                if den_spec == "volume":
                    den_w, den_art = v_week, articles(vol.get(c.id, {}))
                else:
                    den_w = sum((weekly(sig[c.id][k]) for k in den_spec), np.zeros(n_weeks))
                    den_art = sum(articles(sig[c.id][k]) for k in den_spec)
                den_total = int(den_w.sum())
                if (total_events < MIN_EVENTS or den_total == 0 or int((v_week > 0).sum()) < MIN_WEEKS
                        or (den_spec != "volume" and den_total < MIN_SHARE_EVENTS)):
                    IndicatorObservation.objects.filter(indicator=ind, country=c, reporting_period=period,
                                                        source=src).delete()
                    summary["missing"] += 1
                    continue
                value = mult * float(num_w.sum()) / den_total
                lo, hi = bootstrap_ratio_ci(num_w, den_w, mult, seed=_seed(code, c.iso3, period.slug))
                notes = (f"Machine-computed aggregate of {den_total} events from {den_art} source articles; "
                         f"method {METHOD_VERSION}. Numerator: {int(num_w.sum())} events ({num_art} articles) in signal "
                         f"{'+'.join(nums)}; 90% interval by weekly block bootstrap (B={BOOTSTRAP_B}).")
                IndicatorObservation.objects.update_or_create(
                    indicator=ind, country=c, reporting_period=period, reference_label=label, source=src,
                    defaults=dict(value=round(value, 6), ci_low=round(lo, 6), ci_high=round(hi, 6),
                                  sample_size=den_total, reference_start=start, reference_end=end,
                                  data_status=status, source_url="https://www.bnnasia.org/methodology/",
                                  published_at=today, collected_at=now, verified_at=now,
                                  verification_status="verified", is_historical=False, notes=notes))
                summary["written"] += 1
    summary["events_total"] = CountryVolumeDaily.objects.filter(day__gte=start, day__lte=end).aggregate(
        s=Sum("events"))["s"] or 0
    return summary
