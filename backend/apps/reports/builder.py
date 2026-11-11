"""Builds a country report strictly from verified database records.

The deterministic builder assembles every factual sentence from records and attaches
a citation to each. An optional LLM pass (settings.AI_PROVIDER) may only rephrase the
already-cited text – it receives no other facts and its output stays a draft.
"""
from django.db.models import Count

from apps.catalog.models import IntelligenceCategory
from apps.incidents.models import Incident
from apps.observations.models import IndicatorObservation
from apps.rankings.models import CountryScore, RankingSnapshot

from .models import CountryReport


def _cite(obj_type, obj):
    url = getattr(obj, "source_url", "") or ""
    return {"type": obj_type, "id": obj.pk, "url": url,
            "source": str(getattr(obj, "source", "")) if hasattr(obj, "source") else ""}


def build_report(country, period, snapshot: RankingSnapshot | None = None, author=None) -> CountryReport:
    snapshot = snapshot or RankingSnapshot.objects.filter(reporting_period=period, status="published").first()
    sections = {}
    cats = IntelligenceCategory.objects.filter(is_enabled=True, pdf_included=True)

    overall = CountryScore.objects.filter(snapshot=snapshot, country=country, category=None).first() if snapshot else None
    if overall and overall.is_ranked:
        n = CountryScore.objects.filter(snapshot=snapshot, category=None, is_ranked=True).count()
        summary = (f"In the {period.name} BNN Asia Index (methodology v{snapshot.methodology.version}), {country.name} "
                   f"scores {overall.score:.1f}/100 and ranks {overall.rank} of {n} ranked countries "
                   f"(data coverage {overall.coverage:.0%}, confidence {overall.confidence}).")
    else:
        summary = (f"{country.name} is not ranked in the {period.name} BNN Asia Index because the verified data "
                   f"currently available does not meet the coverage threshold.")
    sections["executive_summary"] = {"text": summary, "citations": [{"type": "snapshot", "id": snapshot.pk}] if snapshot else []}
    sections["overview"] = {"text": f"{country.name} ({country.region.name}). Capital: {country.capital or '—'}.", "citations": []}

    for cat in cats:
        obs = (IndicatorObservation.objects.filter(country=country, reporting_period=period, indicator__category=cat,
                                                   verification_status="verified")
               .select_related("indicator", "source").order_by("indicator__display_order"))
        lines, cites = [], []
        for o in obs:
            tag = " (historical reference)" if o.is_historical else ""
            status = "" if o.data_status == "final" else f" [{o.get_data_status_display().lower()}]"
            rank = f", ranked {o.published_rank}/{o.published_rank_of} globally by {o.source.organisation}" if o.published_rank else ""
            lines.append(f"{o.indicator.name}: {o.value:,.2f}{(' ' + o.indicator.unit) if o.indicator.unit else ''} "
                         f"({o.reference_label}{status}{rank}){tag}. [{len(cites) + 1}]")
            cites.append(_cite("observation", o))
        cs = CountryScore.objects.filter(snapshot=snapshot, country=country, category=cat).first() if snapshot else None
        if cs and cs.is_ranked:
            lines.insert(0, f"Category score {cs.score:.1f}/100, rank {cs.rank} in Asia.")
        sections[cat.slug] = {"text": "\n".join(lines) or "No verified data for this period.", "citations": cites}

    inc = (Incident.objects.filter(country=country, reporting_period=period, verification_status="verified",
                                   duplicate_of__isnull=True, is_published=True)
           .select_related("incident_type").order_by("-event_date"))
    lines, cites = [], []
    for i in inc[:25]:
        claim = i.claims.exclude(status="rejected").first()
        lines.append(f"{i.event_date:%d %b %Y} – {i.incident_type.name}: {i.title}. [{len(cites) + 1}]")
        cites.append({"type": "incident", "id": i.pk, "url": claim.source_url if claim else ""})
    counts = inc.values("incident_type__name").annotate(n=Count("id")).order_by("-n")
    sections["incidents"] = {"text": "\n".join(lines) or "No verified incidents recorded for this period.", "citations": cites,
                             "counts": {c["incident_type__name"]: c["n"] for c in counts}}
    sections["methodology"] = {"text": (snapshot.methodology.description + "\n\n" + snapshot.methodology.limitations)
                               if snapshot else "No published methodology yet.", "citations": []}
    sections["sources"] = {"text": "", "citations": [c for s in sections.values() for c in s.get("citations", [])]}

    last = CountryReport.objects.filter(country=country, reporting_period=period).order_by("-version").first()
    return CountryReport.objects.create(
        country=country, reporting_period=period, snapshot=snapshot, author=author,
        title=f"{country.name} – Country Intelligence Report {period.name}", sections=sections,
        version=(last.version + 1) if last else 1)
