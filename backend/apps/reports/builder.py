"""Builds data-driven annual country reports strictly from database records.

Every number in a report is read from (or computed with simple, documented statistics
from) database rows: ranking snapshots, verified indicator observations, published
verified incidents and daily GDELT signal aggregates. Each sentence that states a
number carries a citation to the record it came from. The builder describes patterns
only – it never attributes causes.

Statistics used (all explained in the report's methodology section):
* rate per 1,000 = signal events / all GDELT events located in the country × 1,000
  (corrects for how much a country is covered by the media overall);
* Asian median = median of that rate over all active countries with event data;
* ratio = country rate / Asian median;
* z-score = (country rate − mean) / sample standard deviation across countries
  (computed only with at least MIN_COUNTRIES_Z countries);
* half-period change = % change in the rate between the first and second half of
  the observed days; month-over-month = % change between the last two months.
"""
import calendar
import math
import statistics
from collections import defaultdict

from django.db import transaction
from django.db.models import Count, Max, Min, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone

from apps.catalog.models import IntelligenceCategory
from apps.core.models import Country
from apps.incidents.models import Incident
from apps.observations.models import IndicatorObservation
from apps.rankings.models import CountryScore, RankingSnapshot
from apps.signals.models import CountryVolumeDaily, IngestedDay, SignalDaily
from apps.signals.rules import SIGNALS

from . import charts
from .models import CountryReport

BUILDER_VERSION = "2.0"
MIN_EVENTS_FINDING = 10      # minimum signal events before a deviation/trend becomes a finding
MIN_COUNTRIES_Z = 5          # minimum countries before a z-score is reported
Z_FINDING = 1.0              # |z| from which a deviation counts as notable
TREND_FINDING = 25.0         # |% change| from which a half-period trend counts as notable
MAX_FINDINGS, MIN_FINDINGS = 6, 3
GDELT_URL = "https://www.gdeltproject.org/data.html"
GDELT_SOURCE = "GDELT Event Database (daily export) – BNN Asia daily aggregation"

STATS_NOTE = (
    "Event-data statistics. Signal counts are GDELT events located in the country and matched to the public BNN Asia "
    "signal taxonomy (CAMEO codes and actor types). Counts are expressed per 1,000 of all GDELT events located in the "
    "same country, which adjusts for differences in overall media attention. The Asian median is the median of that rate "
    "across all active countries with event data. A z-score is the distance from the cross-country mean in standard "
    f"deviations and is only reported when at least {MIN_COUNTRIES_Z} countries have data. Trends compare the rate in "
    "the first and second half of the observed days, and the latest month with the preceding one. Deviations and trends "
    f"are only highlighted as findings when the country has at least {MIN_EVENTS_FINDING} matching events.")
EVENT_LIMITATIONS = (
    "Limitations of event data. Event data reflect what the news media report, not everything that happens: coverage "
    "differs between countries, languages and outlets, and attention spikes around major news. Events are coded by "
    "machine from news text, so individual records can be misclassified, duplicated or wrongly located. In restrictive "
    "media environments incidents are under-reported, so a low rate can indicate limited reporting rather than few "
    "incidents. Event-data figures are therefore indicators of reported activity and describe patterns only; they do not "
    "establish causes or responsibility and are not used as verified incident counts.")


# ───────────────────────── helpers ─────────────────────────

def _pair(v):
    """Return (low, high) from [a, b] / (a, b) / {'low','high'} / {'lo','hi'}; else None."""
    if isinstance(v, (list, tuple)) and len(v) == 2 and all(isinstance(x, (int, float)) for x in v):
        return float(v[0]), float(v[1])
    if isinstance(v, dict):
        for a, b in (("low", "high"), ("lo", "hi"), ("lower", "upper")):
            if isinstance(v.get(a), (int, float)) and isinstance(v.get(b), (int, float)):
                return float(v[a]), float(v[b])
    return None


def _z(value, values):
    vals = [v for v in values if v is not None]
    if len(vals) < MIN_COUNTRIES_Z:
        return None
    sd = statistics.stdev(vals)
    if sd <= 0:
        return None
    return (value - statistics.mean(vals)) / sd


def _pct(a, b):
    return (b - a) / a * 100 if a else None


def _fmt_value(v):
    return f"{v:,.0f}" if abs(v) >= 1000 else f"{v:,.2f}"


def _d(day):
    return f"{day.day} {day:%B %Y}"


def _month_name(key):
    y, m = key.split("-")
    return f"{calendar.month_name[int(m)]} {y}"


def _cite(obj_type, obj):
    return {"type": obj_type, "id": obj.pk, "url": getattr(obj, "source_url", "") or "",
            "source": str(obj.source) if getattr(obj, "source_id", None) else ""}


def _editorial_notes(cs):
    """Editorial entries stored by the statistics engine in CountryScore.detail['editorial'] (list, dict or str)."""
    ed = (cs.detail or {}).get("editorial") if cs is not None and isinstance(cs.detail, dict) else None
    items = ed if isinstance(ed, list) else [ed] if ed else []
    out = []
    for e in items:
        if isinstance(e, dict) and e.get("reason"):
            out.append(f"{str(e.get('kind', 'note')).capitalize()}: {e['reason']}")
        elif isinstance(e, str) and e:
            out.append(e)
    return out


class AsiaContext:
    """Cross-country aggregates for one period/snapshot – computed once, reused for every country."""

    def __init__(self, period, snapshot):
        self.period, self.snapshot = period, snapshot
        self.start = period.start_date
        self.end = min(period.end_date, timezone.localdate())
        rng = {"day__gte": self.start, "day__lte": self.end, "country__is_active": True}
        self.volume = {r["country_id"]: r["ev"] for r in CountryVolumeDaily.objects.filter(**rng)
                       .values("country_id").annotate(ev=Sum("events")) if r["ev"]}
        self.signal_totals = {(r["country_id"], r["signal"]): r["ev"] or 0 for r in SignalDaily.objects.filter(
            signal__in=list(SIGNALS), **rng).values("country_id", "signal").annotate(ev=Sum("events"))}
        self.rates = {key: {cid: self.signal_totals.get((cid, key), 0) / vol * 1000 for cid, vol in self.volume.items()}
                      for key in SIGNALS}
        ing = IngestedDay.objects.filter(day__gte=self.start, day__lte=self.end, status="ok")
        self.ingested_days = ing.count()
        self.scores, self.cat_scores = {}, defaultdict(list)
        if snapshot:
            for cs in CountryScore.objects.filter(snapshot=snapshot, country__is_active=True).select_related("country"):
                self.scores[(cs.country_id, cs.category_id)] = cs
                if cs.score is not None:
                    self.cat_scores[cs.category_id].append(cs)

    def ranked_count(self, category_id):
        return sum(1 for cs in self.cat_scores.get(category_id, []) if cs.is_ranked)


class _Cites:
    def __init__(self):
        self.items = []

    def add(self, c):
        self.items.append(c)
        return len(self.items)


# ───────────────────────── sections ─────────────────────────

def _executive_summary(country, period, ctx, findings_count):
    snap, cites = ctx.snapshot, _Cites()
    overall = ctx.scores.get((country.pk, None))
    data = {}
    if overall and overall.is_ranked and overall.score is not None:
        n = ctx.ranked_count(None)
        ref = cites.add({"type": "country_score", "id": overall.pk, "url": "", "source": f"BNN Asia Index snapshot {snap.pk}"})
        parts = [f"In the {period.name} BNN Asia Index (methodology v{snap.methodology.version}), {country.name} scores "
                 f"{overall.score:.1f}/100 and ranks {overall.rank} of {n} ranked countries [{ref}]."]
        detail = overall.detail if isinstance(overall.detail, dict) else {}
        ci, ri = _pair(detail.get("score_ci")), _pair(detail.get("rank_interval"))
        if ci:
            parts.append(f"The uncertainty interval for the score is {ci[0]:.1f}–{ci[1]:.1f}.")
        if ri:
            parts.append(f"Given this uncertainty, the plausible rank range is {ri[0]:.0f}–{ri[1]:.0f}.")
        parts.append(f"Data coverage is {overall.coverage:.0%} of the index weight; confidence is {overall.confidence}.")
        data = {"score": overall.score, "rank": overall.rank, "ranked_countries": n, "coverage": overall.coverage,
                "confidence": overall.confidence, "score_ci": ci, "rank_interval": ri}
        text = " ".join(parts)
    else:
        why = ("no ranking snapshot has been published for this period yet" if not snap else
               "the verified data currently available does not meet the coverage threshold")
        text = (f"{country.name} is not ranked in the {period.name} BNN Asia Index – insufficient data: {why}.")
        if overall:
            data = {"coverage": overall.coverage, "confidence": overall.confidence}
            text += f" Data coverage is {overall.coverage:.0%} of the index weight."
    notes = _editorial_notes(overall)
    if not notes:
        try:
            from apps.signals.models import EditorialAdjustment
            notes = [f"{a.get_kind_display()} ({a.category or 'overall index'}): {a.reason}" for a in
                     EditorialAdjustment.objects.filter(country=country, reporting_period=period, is_active=True)]
        except Exception:  # the signals app is evolving; editorial notes are optional here
            notes = []
    for n in notes:
        text += f"\nEditorial adjustment – {n}"
    data["editorial"] = notes
    if findings_count:
        text += f"\nThis report highlights {findings_count} key findings derived from the largest statistical deviations and trends."
    return {"title": "Executive Summary", "text": text, "citations": cites.items, "data": data}


def _overview(country, period, ctx, n_obs, n_inc):
    days = ctx.ingested_days
    text = (f"{country.name} ({country.region.name}). Capital: {country.capital or '—'}.\n"
            f"This report draws on {n_obs} verified indicator values, {n_inc} published verified incidents and "
            f"{days} days of processed GDELT event data for the {period.name} reporting period "
            f"({_d(period.start_date)} – {_d(period.end_date)}).")
    return {"title": "Country Overview", "text": text, "citations": [],
            "data": {"observations": n_obs, "incidents": n_inc, "event_days": days}}


def _category_section(country, cat, period, ctx, findings):
    cites, lines, indicators = _Cites(), [], []
    obs = (IndicatorObservation.objects.filter(country=country, reporting_period=period, indicator__category=cat,
                                               verification_status="verified")
           .select_related("indicator", "source").order_by("indicator__display_order", "indicator__name", "-reference_end"))
    cs = ctx.scores.get((country.pk, cat.pk))
    peers = ctx.cat_scores.get(cat.pk, [])
    median = statistics.median([p.score for p in peers]) if peers else None
    data = {"score": None, "rank": None, "median": median, "scored_countries": len(peers)}
    if cs and cs.score is not None:
        s = f"{country.name} scores {cs.score:.1f}/100 in {cat.name}"
        if cs.is_ranked and cs.rank:
            s += f", rank {cs.rank} of {ctx.ranked_count(cat.pk)} ranked Asian countries"
        s += "."
        if median is not None:
            diff = cs.score - median
            s += (f" The Asian median for this category is {median:.1f}, so the score is "
                  f"{abs(diff):.1f} points {'above' if diff >= 0 else 'below'} the median.")
        ci = _pair((cs.detail or {}).get("score_ci")) if isinstance(cs.detail, dict) else None
        if ci:
            s += f" Uncertainty interval: {ci[0]:.1f}–{ci[1]:.1f}."
        lines.append(s)
        lines += [f"Editorial adjustment – {n}" for n in _editorial_notes(cs)]
        data.update(score=cs.score, rank=cs.rank, score_ci=ci, coverage=cs.coverage)
        z = _z(cs.score, [p.score for p in peers])
        if z is not None and median is not None:
            diff = cs.score - median
            findings.append({
                "weight": abs(z),
                "text": (f"{cat.name}: the score of {cs.score:.1f} is {abs(diff):.1f} points "
                         f"{'above' if diff >= 0 else 'below'} the Asian median of {median:.1f} "
                         f"(z-score {z:+.1f} across {len(peers)} scored countries)."),
                "citation": {"type": "country_score", "id": cs.pk, "url": "", "source": f"BNN Asia Index snapshot {ctx.snapshot.pk}"},
                "values": {"score": round(cs.score, 1), "median": round(median, 1), "z": round(z, 1), "n": len(peers)}})
    elif ctx.snapshot:
        lines.append(f"No {cat.name} score: the verified data for {country.name} does not meet the category coverage threshold.")
    else:
        lines.append("No ranking snapshot has been published for this period yet, so no category score is available.")

    names = {}
    for o in obs:
        n = cites.add(_cite("observation", o))
        ci_low, ci_high = getattr(o, "ci_low", None), getattr(o, "ci_high", None)
        indicators.append({
            "n": n, "name": o.indicator.name, "value": _fmt_value(o.value), "unit": o.indicator.unit,
            "reference": o.reference_label, "status": o.get_data_status_display(), "historical": o.is_historical,
            "ci": f"{_fmt_value(ci_low)} – {_fmt_value(ci_high)}" if ci_low is not None and ci_high is not None else "",
            "published_rank": f"{o.published_rank}/{o.published_rank_of}" if o.published_rank else "",
            "source": o.source.organisation or o.source.name, "url": o.source_url})
        names.setdefault(o.indicator.name, []).append(str(n))
    if names:
        lines.append("Indicators with verified data: " + "; ".join(f"{k} [{', '.join(v)}]" for k, v in names.items()) + ".")
        hist = sum(1 for i in indicators if i["historical"])
        if hist:
            lines.append(f"{hist} of these values are historical references for comparison and do not count towards scores.")
        prov = sum(1 for i in indicators if i["status"] != "Final")
        if prov:
            lines.append(f"{prov} of {len(indicators)} values are preliminary or estimated and may be revised by the source.")
    else:
        lines.append("No verified indicator data for this period.")
    return {"title": cat.name, "kind": "category", "text": "\n".join(lines), "citations": cites.items,
            "indicators": indicators, "data": data}


def _event_section(country, ctx, findings):
    cid = country.pk
    vol_total = ctx.volume.get(cid, 0)
    base = {"title": "Event Data Analysis", "kind": "events", "citations": [], "signals": [], "evidence": [],
            "months": [], "data": {"volume": vol_total}}
    if not vol_total:
        base["text"] = (f"No GDELT event data has been processed for {country.name} in this period yet, so no event-data "
                        "statistics are reported.")
        return base
    rng = {"country": country, "day__gte": ctx.start, "day__lte": ctx.end}
    vrows = CountryVolumeDaily.objects.filter(**rng)
    first, last = vrows.aggregate(a=Min("day"), b=Max("day")).values()
    mid = first + (last - first) / 2
    month_vol = {r["m"].strftime("%Y-%m"): r["ev"] for r in vrows.annotate(m=TruncMonth("day")).values("m")
                 .annotate(ev=Sum("events")) if r["ev"]}
    srows = SignalDaily.objects.filter(signal__in=list(SIGNALS), **rng)
    month_sig = defaultdict(dict)
    for r in srows.annotate(m=TruncMonth("day")).values("m", "signal").annotate(ev=Sum("events")):
        month_sig[r["signal"]][r["m"].strftime("%Y-%m")] = r["ev"] or 0
    vol_h = [vrows.filter(day__lte=mid).aggregate(s=Sum("events"))["s"] or 0,
             vrows.filter(day__gt=mid).aggregate(s=Sum("events"))["s"] or 0]
    sig_h = [{r["signal"]: r["ev"] for r in srows.filter(day__lte=mid).values("signal").annotate(ev=Sum("events"))},
             {r["signal"]: r["ev"] for r in srows.filter(day__gt=mid).values("signal").annotate(ev=Sum("events"))}]
    months = sorted(month_vol)
    # The month containing the last data day is incomplete unless that day is the month's last day: it is
    # counted in totals but left out of month-over-month comparisons and the trend chart (too few days).
    if months and last.day != calendar.monthrange(last.year, last.month)[1]:
        trend_months = [m for m in months if m != last.strftime("%Y-%m")]
    else:
        trend_months = months
    cites = _Cites()
    lines = [f"Between {_d(first)} and {_d(last)}, GDELT recorded {vol_total:,} events located in "
             f"{country.name}. Signal counts below are expressed per 1,000 of these in-country events and compared "
             f"with the median rate across {len(ctx.volume)} Asian countries with event data."]
    signals, gdelt_n = [], None
    for key, (label, cat_slug, *_rest) in SIGNALS.items():
        total = ctx.signal_totals.get((cid, key), 0)
        rate = total / vol_total * 1000
        peers = list(ctx.rates[key].values())
        median = statistics.median(peers) if peers else None
        ratio = rate / median if median else None
        z = _z(rate, peers)
        per_month = {m: month_sig[key].get(m, 0) for m in months}
        peak = max(months, key=lambda m: per_month[m]) if months and total else None
        mrates = [per_month[m] / month_vol[m] * 1000 for m in trend_months]
        mom = None
        if len(trend_months) >= 2 and min(per_month[m] for m in trend_months[-2:]) >= MIN_EVENTS_FINDING:
            mom = _pct(mrates[-2], mrates[-1])
        h_events = [sig_h[0].get(key, 0), sig_h[1].get(key, 0)]
        h_rates = [h_events[i] / vol_h[i] * 1000 if vol_h[i] else None for i in (0, 1)]
        half = _pct(h_rates[0], h_rates[1]) if None not in h_rates else None
        rec = {"key": key, "label": label, "category": cat_slug, "events": total, "rate": round(rate, 2),
               "median_rate": round(median, 2) if median is not None else None,
               "ratio": round(ratio, 1) if ratio is not None else None, "z": round(z, 1) if z is not None else None,
               "peak_month": _month_name(peak) if peak else "", "peak_events": per_month.get(peak, 0) if peak else 0,
               "mom_change": round(mom) if mom is not None else None,
               "half_change": round(half) if half is not None else None, "half_events": h_events,
               "half_rates": [round(r, 2) if r is not None else None for r in h_rates],
               "monthly_rates": [round(r, 3) for r in mrates]}
        signals.append(rec)
        if not total:
            continue
        cite = {"type": "signal_daily", "signal": key, "country": country.iso3, "from": first.isoformat(),
                "to": last.isoformat(), "url": GDELT_URL, "source": GDELT_SOURCE}
        fcite = {**cite, "source": f"{GDELT_SOURCE} – signal: {label}"}   # findings cite the specific signal
        if gdelt_n is None:   # one shared reference for all signal lines of this section
            gdelt_n = cites.add({**cite, "signal": "all"})
        n = gdelt_n
        s = f"{label}: {total:,} events, {rate:.2f} per 1,000 in-country events"
        if median is not None:
            s += f" (Asian median {median:.2f}" + (f", {ratio:.1f}× the median" if ratio is not None else "") + ")"
        s += f". Highest monthly activity: {rec['peak_month']} ({rec['peak_events']:,} events)."
        if mom is not None:
            s += (f" Latest complete month vs previous ({_month_name(trend_months[-1])} vs "
                  f"{_month_name(trend_months[-2])}): {mom:+.0f}% in the rate.")
        lines.append(s + f" [{n}]")
        # findings candidates
        if total >= MIN_EVENTS_FINDING and median:
            if z is not None and abs(z) >= Z_FINDING:
                findings.append({"weight": abs(z), "citation": fcite,
                                 "text": (f"The rate of {label[0].lower() + label[1:]} ({rate:.2f} per 1,000 in-country "
                                          f"events) is {ratio:.1f}× the Asian median of {median:.2f} (z-score {z:+.1f} "
                                          f"across {len(peers)} countries)."),
                                 "values": {"rate": round(rate, 2), "median": round(median, 2), "ratio": round(ratio, 1),
                                            "z": round(z, 1), "n": len(peers)}})
            elif z is None and (ratio >= 2 or ratio <= 0.5):
                findings.append({"weight": abs(math.log2(ratio)) if ratio > 0 else 1.0, "citation": fcite,
                                 "text": (f"The rate of {label[0].lower() + label[1:]} ({rate:.2f} per 1,000 in-country "
                                          f"events) is {ratio:.1f}× the Asian median of {median:.2f}."),
                                 "values": {"rate": round(rate, 2), "median": round(median, 2), "ratio": round(ratio, 1)}})
        if half is not None and min(h_events) >= MIN_EVENTS_FINDING and abs(half) >= TREND_FINDING:
            findings.append({"weight": abs(half) / 50, "citation": fcite,
                             "text": (f"{label} changed by {half:+.0f}% between the first and the second half of the "
                                      f"observed period ({h_rates[0]:.2f} → {h_rates[1]:.2f} per 1,000 in-country events)."),
                             "values": {"half_change": round(half), "rate_h1": round(h_rates[0], 2),
                                        "rate_h2": round(h_rates[1], 2)}})
    if not any(s["events"] for s in signals):
        lines.append("None of the BNN Asia event signals matched events located in this country in the observed period.")
    # Evidence: one article from the most active day of each signal, most deviating signals first.
    evidence, seen = [], set()
    ranked = sorted((x for x in signals if x["events"]), key=lambda x: -(x["ratio"] or 0))
    for x in ranked:
        if len(evidence) >= 5:
            break
        for r in srows.filter(signal=x["key"]).exclude(sample_urls=[]).order_by("-events", "-day")[:3]:
            u = next((u for u in (r.sample_urls or []) if u and u not in seen), None)
            if u:
                seen.add(u)
                evidence.append({"url": u, "signal": x["label"], "day": r.day.isoformat()})
                break
    if evidence:
        refs = []
        for e in evidence:
            refs.append(f"[{cites.add({'type': 'evidence', 'url': e['url'], 'source': f'Source article ({e['signal']}, {e['day']})'})}]")
        lines.append("Example source articles for the most active days (evidence trail, not verified by BNN Asia): "
                     + " ".join(refs) + ".")
    base.update(text="\n".join(lines), citations=cites.items, signals=signals, evidence=evidence, months=trend_months,
                data={"volume": vol_total, "first_day": first.isoformat(), "last_day": last.isoformat(),
                      "countries_with_data": len(ctx.volume)})
    return base


def _incidents_section(country, period):
    inc = (Incident.objects.filter(country=country, reporting_period=period, verification_status="verified",
                                   duplicate_of__isnull=True, is_published=True)
           .select_related("incident_type").order_by("-event_date"))
    cites, lines = _Cites(), []
    for i in inc[:25]:
        claim = i.claims.exclude(status="rejected").select_related("source").first()
        n = cites.add({"type": "incident", "id": i.pk, "url": claim.source_url if claim else "",
                       "source": str(claim.source) if claim else "BNN Asia verified incident database"})
        lines.append(f"{i.event_date:%d %b %Y} – {i.incident_type.name}: {i.title}. [{n}]")
    counts = {c["incident_type__name"]: c["n"] for c in inc.values("incident_type__name").annotate(n=Count("id")).order_by("-n")}
    total = sum(counts.values())
    if total:
        lines.insert(0, f"{total} verified, published and de-duplicated incidents were recorded for {country.name} in this "
                        "period: " + ", ".join(f"{k} ({v})" for k, v in counts.items()) + ".")
    return {"title": "Major Verified Incidents", "text": "\n".join(lines) or "No verified incidents recorded for this period.",
            "citations": cites.items, "counts": counts}


def _findings_section(findings):
    findings = sorted(findings, key=lambda f: -f["weight"])
    chosen = [f for f in findings if f["weight"] >= 1.0][:MAX_FINDINGS]
    for f in findings:
        if len(chosen) >= MIN_FINDINGS:
            break
        if f not in chosen:
            chosen.append(f)
    cites, lines, items = _Cites(), [], []
    for f in chosen:
        n = cites.add(f["citation"])
        lines.append(f"{f['text']} [{n}]")
        items.append({"text": f["text"], "citation": n, "values": f["values"]})
    return {"title": "Key Findings", "kind": "findings", "items": items, "citations": cites.items,
            "text": "\n".join(lines) or "The available data are not yet sufficient to derive statistical findings."}


def _methodology_section(snapshot):
    if snapshot:
        m = snapshot.methodology
        head = f"{m.name} methodology v{m.version} (aggregation mode: {m.get_mode_display().split(' –')[0]})."
        parts = [head, m.description.strip(), ("Limitations. " + m.limitations.strip()) if m.limitations.strip() else ""]
    else:
        parts = ["No ranking methodology has been published for this period yet; category and index scores are therefore "
                 "not available in this edition of the report."]
    parts += [STATS_NOTE, EVENT_LIMITATIONS,
              "Report generation. This report is generated automatically from the BNN Asia database and may afterwards be "
              "edited by BNN Asia editors. Each regeneration creates a new version; earlier versions are kept."]
    return {"title": "Methodology and Limitations", "kind": "methodology", "text": "\n\n".join(p for p in parts if p),
            "citations": [], "methodology_version": snapshot.methodology.version if snapshot else None}


# ───────────────────────── charts ─────────────────────────

def _charts(country, period, version, ctx, event_sec, cat_secs):
    stem = f"{country.slug}-{period.slug}-v{version}"
    out = []
    sig = sorted((s for s in event_sec.get("signals", []) if s["events"]), key=lambda s: -s["events"])[:4]
    months = event_sec.get("months", [])
    if sig and len(months) >= 2:
        path = charts.trend_chart(f"{stem}-1.png", months, [(s["label"], s["monthly_rates"]) for s in sig], country.name)
        out.append({"title": "Monthly trend of the main event-data signals", "path": path, "section": "event_data",
                    "alt": f"Line chart of monthly rates per 1,000 in-country events for {', '.join(s['label'] for s in sig)} "
                           f"in {country.name}, {_month_name(months[0])} to {_month_name(months[-1])}."})
    rows = [(sec["title"], sec["data"]["score"], sec["data"]["median"]) for sec in cat_secs if sec["data"].get("score") is not None]
    if rows:
        path = charts.category_chart(f"{stem}-2.png", rows, country.name)
        out.append({"title": "Category scores compared with the Asian median", "path": path, "section": "executive_summary",
                    "alt": "Bar chart of category scores: " + "; ".join(
                        f"{r[0]} {r[1]:.1f}" + (f" (median {r[2]:.1f})" if r[2] is not None else "") for r in rows) + "."})
    overall = ctx.scores.get((country.pk, None))
    ranked = [cs for cs in ctx.cat_scores.get(None, []) if cs.is_ranked]
    if overall and overall.is_ranked and overall.score is not None and len(ranked) >= 3:
        med = statistics.median([cs.score for cs in ranked])
        path = charts.position_chart(f"{stem}-3.png", [(cs.country.iso3, cs.score) for cs in ranked], country.iso3, med)
        out.append({"title": "Position among Asian countries (overall index)", "path": path, "section": "executive_summary",
                    "alt": f"Dot plot of overall scores of {len(ranked)} ranked Asian countries; {country.name} scores "
                           f"{overall.score:.1f} and ranks {overall.rank}; the median is {med:.1f}."})
    return out


# ───────────────────────── entry point ─────────────────────────

def default_snapshot(period):
    return RankingSnapshot.objects.filter(reporting_period=period, status="published").order_by("-published_at", "-pk").first()


def build_report(country, period, snapshot: RankingSnapshot | None = None, author=None, publish=True, *,
                 force=False, context: AsiaContext | None = None) -> CountryReport:
    """Create a new report version for country/period.

    If the latest version is locked by an editor (and force is False) nothing is generated and the
    locked report is returned with ``skipped_locked = True``. Older versions are never modified,
    except that a newly published version marks previously published ones as superseded.
    """
    snapshot = snapshot or (context.snapshot if context else None) or default_snapshot(period)
    with transaction.atomic():
        latest = (CountryReport.objects.select_for_update().filter(country=country, reporting_period=period)
                  .order_by("-version").first())
        if latest and latest.locked and not force:
            latest.skipped_locked = True
            return latest
        version = latest.version + 1 if latest else 1
        ctx = context if context and context.snapshot == snapshot and context.period == period else AsiaContext(period, snapshot)

        findings = []
        cats = IntelligenceCategory.objects.filter(is_enabled=True, pdf_included=True).order_by("display_order", "name")
        cat_secs = [(cat.slug, _category_section(country, cat, period, ctx, findings)) for cat in cats]
        events = _event_section(country, ctx, findings)
        if ctx.snapshot:
            overall = ctx.scores.get((country.pk, None))
            ranked = [cs.score for cs in ctx.cat_scores.get(None, []) if cs.is_ranked]
            if overall and overall.is_ranked and overall.score is not None:
                z = _z(overall.score, ranked)
                med = statistics.median(ranked) if ranked else overall.score
                findings.append({
                    "weight": abs(z) if z is not None else 0.5,
                    "text": (f"Overall, {country.name} ranks {overall.rank} of {len(ranked)} ranked Asian countries with a "
                             f"BNN Asia Index score of {overall.score:.1f} (Asian median {med:.1f}"
                             + (f", z-score {z:+.1f})." if z is not None else ").")),
                    "citation": {"type": "country_score", "id": overall.pk, "url": "",
                                 "source": f"BNN Asia Index snapshot {ctx.snapshot.pk}"},
                    "values": {"rank": overall.rank, "n": len(ranked), "score": round(overall.score, 1),
                               "median": round(med, 1), "z": round(z, 1) if z is not None else None}})
        findings_sec = _findings_section(findings)
        n_obs = sum(len(s["indicators"]) for _, s in cat_secs)
        incidents = _incidents_section(country, period)
        n_inc = sum(incidents["counts"].values())

        sections = {
            "executive_summary": _executive_summary(country, period, ctx, len(findings_sec["items"])),
            "findings": findings_sec,
            "overview": _overview(country, period, ctx, n_obs, n_inc),
            **dict(cat_secs),
            "event_data": events,
            "incidents": incidents,
            "methodology": _methodology_section(snapshot),
        }
        seen, refs = set(), []
        for sec in sections.values():
            for c in sec.get("citations", []):
                k = (c.get("type"), c.get("id"), c.get("url"), c.get("from"), c.get("to"))
                if k not in seen:
                    seen.add(k)
                    refs.append(c)
        sections["sources"] = {"title": "Sources and References", "kind": "sources", "text": "", "citations": refs}
        sections["charts"] = _charts(country, period, version, ctx, events, [s for _, s in cat_secs])
        sections["_meta"] = {
            "order": ["executive_summary", "findings", "overview", *[k for k, _ in cat_secs], "event_data", "incidents",
                      "methodology", "sources"],
            "builder_version": BUILDER_VERSION, "generated_at": timezone.now().isoformat(),
            "methodology_version": snapshot.methodology.version if snapshot else None,
            "snapshot_id": snapshot.pk if snapshot else None,
            "event_window": [ctx.start.isoformat(), ctx.end.isoformat()],
        }
        now = timezone.now()
        report = CountryReport.objects.create(
            country=country, reporting_period=period, snapshot=snapshot, author=author,
            title=f"{country.name} – Annual Country Intelligence Report {period.name}", sections=sections,
            version=version, status="published" if publish else "draft", published_at=now if publish else None)
        if publish:
            supersede_older(report)
        report.skipped_locked = False
        return report


def supersede_older(report):
    """Only the newest published version of a country/period is current; older ones stay readable."""
    for old in CountryReport.objects.filter(country=report.country, reporting_period=report.reporting_period,
                                            status="published").exclude(pk=report.pk):
        old.status = "superseded"
        old.save(update_fields=["status", "updated_at"])   # saved one by one so the audit log records it


def build_all(period=None, iso3=None, publish=True, author=None, stdout=None):
    """Build reports for all active countries (or one). Returns list of (country, report, skipped)."""
    from apps.core.models import ReportingPeriod
    period = period or ReportingPeriod.current()
    snapshot = default_snapshot(period)
    ctx = AsiaContext(period, snapshot)
    qs = Country.objects.filter(is_active=True).select_related("region")
    if iso3:
        qs = qs.filter(iso3=iso3.upper())
    out = []
    for c in qs:
        r = build_report(c, period, snapshot, author=author, publish=publish, context=ctx)
        out.append((c, r, r.skipped_locked))
        if stdout:
            stdout(c, r)
    return out
