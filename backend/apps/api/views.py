"""Public, read-only API. Only *published / verified / visible* data is ever returned."""
import csv

from django.db.models import Count, Max, Min, Q, Sum
from django.http import Http404, StreamingHttpResponse
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from rest_framework import viewsets
from rest_framework.decorators import action, api_view
from rest_framework.response import Response

from apps.catalog.models import Indicator, IntelligenceCategory
from apps.core.models import Country, ReportingPeriod
from apps.incidents.models import Incident
from apps.observations.models import IndicatorObservation
from apps.rankings.models import CountryScore, RankingSnapshot
from apps.reports.models import CountryReport

from . import serializers as s

CACHE = 300


def period_from(request):
    slug = request.query_params.get("period")
    return get_object_or_404(ReportingPeriod, slug=slug) if slug else ReportingPeriod.current()


def visible_categories():
    return IntelligenceCategory.objects.filter(is_enabled=True, public_visible=True)


def public_observations(period):
    return (IndicatorObservation.objects.filter(reporting_period=period, verification_status="verified",
                                                indicator__category__in=visible_categories(), indicator__is_active=True)
            .select_related("indicator__category", "source"))


@method_decorator(cache_page(CACHE), name="dispatch")
class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = s.CategorySerializer
    lookup_field = "slug"
    pagination_class = None

    def get_queryset(self):
        return visible_categories()


@method_decorator(cache_page(CACHE), name="dispatch")
class IndicatorViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = s.IndicatorSerializer
    lookup_field = "code"
    pagination_class = None

    def get_queryset(self):
        return Indicator.objects.filter(is_active=True, category__in=visible_categories()).select_related("category", "primary_source")


@method_decorator(cache_page(CACHE), name="dispatch")
class CountryViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = s.CountrySerializer
    lookup_field = "slug"
    pagination_class = None
    filterset_fields = ["region__slug"]

    def get_queryset(self):
        return Country.objects.filter(is_active=True).select_related("region")

    @action(detail=True)
    def profile(self, request, slug=None):
        c = self.get_object()
        period = period_from(request)
        obs = public_observations(period).filter(country=c).order_by("indicator__category__display_order", "indicator__display_order")
        snap = RankingSnapshot.objects.filter(reporting_period=period, status="published").first()
        scores = CountryScore.objects.filter(snapshot=snap, country=c).filter(
            Q(category__isnull=True) | Q(category__in=visible_categories())).select_related("category", "country__region") if snap else []
        inc = Incident.objects.filter(country=c, reporting_period=period, is_published=True, duplicate_of__isnull=True,
                                      incident_type__category__in=visible_categories()).select_related("incident_type__category")
        counts = {}
        for i in inc:
            counts[i.incident_type.name] = counts.get(i.incident_type.name, 0) + 1
        return Response({
            "country": s.CountrySerializer(c).data,
            "period": s.PeriodSerializer(period).data,
            "categories": s.CategorySerializer(visible_categories(), many=True).data,
            "observations": s.ObservationSerializer(obs, many=True).data,
            "scores": s.ScoreSerializer(scores, many=True).data,
            "snapshot": s.SnapshotSerializer(snap).data if snap else None,
            "incident_counts": counts,
            "recent_incidents": s.IncidentSerializer(inc.order_by("-event_date")[:10], many=True).data,
            "reports": s.ReportSerializer(CountryReport.objects.filter(country=c, reporting_period=period, status="published"),
                                          many=True, context={"request": request}).data,
            "last_updated": max([o.collected_at for o in obs], default=None),
        })


@method_decorator(cache_page(CACHE), name="dispatch")
class IncidentViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = s.IncidentSerializer
    filterset_fields = {"country__slug": ["exact"], "incident_type__slug": ["exact"], "event_date": ["gte", "lte"]}
    ordering_fields = ["event_date"]

    def get_queryset(self):
        return (Incident.objects.filter(is_published=True, verification_status="verified", duplicate_of__isnull=True,
                                        reporting_period=period_from(self.request),
                                        incident_type__category__in=visible_categories())
                .select_related("country", "incident_type__category").prefetch_related("claims__source").order_by("-event_date"))


@api_view(["GET"])
def ranking(request):
    """BNN Asia Index (published snapshot). ?category=slug for a category ranking."""
    period = period_from(request)
    snap = RankingSnapshot.objects.filter(reporting_period=period, status="published").first()
    if not snap:
        return Response({"period": period.slug, "available": False, "message": "No published ranking yet for this period."})
    cat = request.query_params.get("category")
    qs = CountryScore.objects.filter(snapshot=snap).select_related("country__region", "category")
    if cat:
        c = get_object_or_404(visible_categories(), slug=cat)
        if not c.ranked:
            return Response({"available": False, "message": f"{c.name} is currently excluded from ranking."})
        qs = qs.filter(category=c)
    else:
        qs = qs.filter(category__isnull=True)
    rows = sorted(qs, key=lambda x: (not x.is_ranked, x.rank or 10**6, x.country.name))
    return Response({"period": period.slug, "available": snap.overall_available or bool(cat),
                     "label": "BNN Asia Index – calculated by BNN Asia", "snapshot": s.SnapshotSerializer(snap).data,
                     "results": s.ScoreSerializer(rows, many=True).data})


@api_view(["GET"])
def official_rankings(request):
    """Published global rankings from source organisations + BNN-calculated Asia-only position.
    ?indicator=ti_cpi_score|rsf_score|..."""
    period = period_from(request)
    code = request.query_params.get("indicator", "ti_cpi_score")
    obs = list(public_observations(period).filter(indicator__code=code, is_historical=False).order_by("-reference_end"))
    latest_label = obs[0].reference_label if obs else None
    obs = [o for o in obs if o.reference_label == latest_label]
    better_high = obs[0].indicator.direction == "higher_better" if obs else True
    obs.sort(key=lambda o: -o.value if better_high else o.value)
    out, last, pos = [], None, 0
    for i, o in enumerate(obs, start=1):
        if o.value != last:
            pos, last = i, o.value
        out.append({"country": s.CountrySerializer(o.country).data, "value": o.value,
                    "official_global_rank": o.published_rank, "official_global_of": o.published_rank_of,
                    "bnn_asia_position": pos, "source": o.source.organisation, "source_url": o.source_url,
                    "reference": o.reference_label, "published_at": o.published_at})
    return Response({"indicator": code, "edition": latest_label,
                     "note": "Official global ranks are published by the source organisation. 'bnn_asia_position' is "
                             "BNN Asia's own re-ordering of Asian countries and is not an official ranking of that organisation.",
                     "results": out})


@api_view(["GET"])
def compare(request):
    """?countries=bangladesh,india,pakistan&indicators=ti_cpi_score,wgi_rl"""
    period = period_from(request)
    slugs = [x for x in request.query_params.get("countries", "").split(",") if x][:6]
    codes = [x for x in request.query_params.get("indicators", "").split(",") if x]
    obs = public_observations(period).filter(country__slug__in=slugs, is_historical=False)
    if codes:
        obs = obs.filter(indicator__code__in=codes)
    data = {}
    for o in obs.order_by("-reference_end"):
        data.setdefault(o.indicator.code, {"name": o.indicator.name, "unit": o.indicator.unit, "values": {}})
        data[o.indicator.code]["values"].setdefault(o.country.slug, {"value": o.value, "ref": o.reference_label,
                                                                     "source_url": o.source_url})
    return Response({"countries": slugs, "indicators": data})


@api_view(["GET"])
def site_config(request):
    """Everything the WordPress plugin needs to decide what to show."""
    period = period_from(request)
    return Response({"period": s.PeriodSerializer(period).data,
                     "periods": s.PeriodSerializer(ReportingPeriod.objects.exclude(status="draft"), many=True).data,
                     "categories": s.CategorySerializer(visible_categories(), many=True).data,
                     "has_published_ranking": RankingSnapshot.objects.filter(reporting_period=period, status="published").exists()})


def _published_snapshot(period):
    return (RankingSnapshot.objects.filter(reporting_period=period, status="published")
            .select_related("methodology").order_by("-published_at").first())


class _Echo:
    def write(self, value):
        return value


CSV_COLUMNS = ["period", "methodology_version", "snapshot_id", "published_at", "category", "rank", "country", "iso3",
               "region", "score", "score_ci_low", "score_ci_high", "rank_best", "rank_worst", "previous_rank",
               "coverage", "confidence", "is_ranked", "status_label", "imputed_categories", "editorial"]


@api_view(["GET"])
def ranking_csv(request):
    """Open-data download of the published BNN Asia Index as CSV. ?category=slug, ?period=slug."""
    period = period_from(request)
    snap = _published_snapshot(period)
    if not snap:
        raise Http404("No published ranking yet for this period.")
    cat = request.query_params.get("category")
    qs = CountryScore.objects.filter(snapshot=snap).select_related("country__region", "category")
    if cat:
        c = get_object_or_404(visible_categories(), slug=cat)
        if not c.ranked:
            raise Http404(f"{c.name} is currently excluded from ranking.")
        qs = qs.filter(category=c)
    else:
        qs = qs.filter(category__isnull=True)
    rows = sorted(qs, key=lambda x: (not x.is_ranked, x.rank or 10**6, x.country.name))
    slug_of = {c.id: c.slug for c in IntelligenceCategory.objects.all()}

    def gen():
        w = csv.writer(_Echo())
        yield w.writerow(CSV_COLUMNS)
        for r in rows:
            d = r.detail or {}
            ci = d.get("score_ci") or [None, None]
            ri = d.get("rank_interval") or [None, None]
            ed = "; ".join(f"{e.get('kind')}: {e.get('reason')}" for e in d.get("editorial", []))
            yield w.writerow([period.slug, snap.methodology.version, snap.pk,
                              snap.published_at.isoformat() if snap.published_at else "",
                              r.category.slug if r.category else "overall", r.rank or "", r.country.name,
                              r.country.iso3, r.country.region.name, "" if r.score is None else r.score,
                              "" if ci[0] is None else ci[0], "" if ci[1] is None else ci[1],
                              "" if ri[0] is None else ri[0], "" if ri[1] is None else ri[1], r.previous_rank or "",
                              r.coverage, r.confidence, int(r.is_ranked), r.status_label,
                              ",".join(slug_of.get(i, str(i)) for i in r.imputed_categories), ed])

    name = f"bnn-asia-index-{period.slug}{'-' + cat if cat else ''}.csv"
    resp = StreamingHttpResponse(gen(), content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="{name}"'
    return resp


@api_view(["GET"])
def methodology(request):
    """Current published methodology, public signal rules, indicator list and data-volume statistics."""
    from apps.rankings.models import RankingMethodology
    from apps.signals.models import CountryVolumeDaily, IngestedDay, SignalDaily
    from apps.signals.rules import SIGNALS

    period = period_from(request)
    snap = _published_snapshot(period)
    m = snap.methodology if snap else (RankingMethodology.objects.filter(reporting_period=period, is_published=True)
                                       .order_by("-published_at").first())
    meth = None
    if m:
        meth = {"name": m.name, "version": m.version, "mode": m.mode, "min_coverage": m.min_coverage,
                "min_category_coverage": m.min_category_coverage, "description": m.description,
                "limitations": m.limitations, "published_at": m.published_at,
                "weights": [{"category": w.category.slug, "name": w.category.name, "weight": w.weight,
                             "ranked": w.category.ranked} for w in m.weights.select_related("category")]}
        if snap:
            slugs = dict(IntelligenceCategory.objects.values_list("id", "slug"))
            meth["effective_weights"] = {slugs.get(int(k), k): v for k, v in snap.effective_weights.items()}
    visible = set(visible_categories().values_list("slug", flat=True))
    rules = [{"key": k, "label": lab, "category": cat, "category_visible": cat in visible, "cameo_prefixes": list(codes),
              "target_types": sorted(t) if t else None, "perpetrator_types": sorted(p) if p else None}
             for k, (lab, cat, codes, t, p) in SIGNALS.items()]
    inds = Indicator.objects.filter(is_active=True, category__in=visible_categories()).select_related(
        "category", "primary_source")
    days = IngestedDay.objects.filter(status="ok", day__gte=period.start_date, day__lte=period.end_date)
    dstats = days.aggregate(n=Count("id"), rows=Sum("rows_total"), asia=Sum("rows_asia"), first=Min("day"),
                            last=Max("day"), updated=Max("processed_at"))
    vol = CountryVolumeDaily.objects.filter(day__gte=period.start_date, day__lte=period.end_date).aggregate(
        events=Sum("events"), articles=Sum("articles"), countries=Count("country", distinct=True))
    sig = dict(SignalDaily.objects.filter(day__gte=period.start_date, day__lte=period.end_date)
               .values_list("signal").annotate(n=Sum("events")))
    return Response({
        "period": period.slug,
        "methodology": meth,
        "signals": rules,
        "indicators": s.MethodologyIndicatorSerializer(inds, many=True).data,
        "data_volume": {"days_ingested": dstats["n"] or 0, "first_day": dstats["first"], "last_day": dstats["last"],
                        "gdelt_rows_processed": dstats["rows"] or 0, "asia_rows": dstats["asia"] or 0,
                        "events_in_countries": vol["events"] or 0, "source_articles": vol["articles"] or 0,
                        "countries_with_data": vol["countries"] or 0,
                        "signal_events": {k: sig.get(k, 0) for k in SIGNALS},
                        "last_update": dstats["updated"]},
        "snapshot": s.SnapshotSerializer(snap).data if snap else None,
    })


@api_view(["GET"])
def health(request):
    return Response({"status": "ok"})
