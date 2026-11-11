from rest_framework import serializers

from apps.catalog.models import Indicator, IntelligenceCategory
from apps.core.models import Country, ReportingPeriod
from apps.incidents.models import Incident
from apps.observations.models import IndicatorObservation
from apps.rankings.models import CountryScore, RankingSnapshot
from apps.reports.models import CountryReport


class PeriodSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReportingPeriod
        fields = ["name", "slug", "start_date", "end_date", "status", "is_current"]


class CategorySerializer(serializers.ModelSerializer):
    ranked = serializers.BooleanField(read_only=True)
    in_pdf = serializers.BooleanField(read_only=True)

    class Meta:
        model = IntelligenceCategory
        fields = ["name", "slug", "description", "methodology", "display_order", "icon", "ranked", "in_pdf", "version"]


class IndicatorSerializer(serializers.ModelSerializer):
    category = serializers.SlugRelatedField(slug_field="slug", read_only=True)
    source = serializers.CharField(source="primary_source.organisation", default="", read_only=True)

    class Meta:
        model = Indicator
        fields = ["code", "name", "category", "unit", "value_type", "direction", "source", "used_in_scoring"]


class CountrySerializer(serializers.ModelSerializer):
    region = serializers.CharField(source="region.name")

    class Meta:
        model = Country
        fields = ["name", "slug", "iso2", "iso3", "region", "capital", "flag_emoji"]


class ObservationSerializer(serializers.ModelSerializer):
    indicator = serializers.CharField(source="indicator.code")
    indicator_name = serializers.CharField(source="indicator.name")
    category = serializers.CharField(source="indicator.category.slug")
    unit = serializers.CharField(source="indicator.unit")
    source = serializers.CharField(source="source.organisation")

    class Meta:
        model = IndicatorObservation
        fields = ["indicator", "indicator_name", "category", "unit", "value", "reference_label", "reference_start",
                  "reference_end", "data_status", "is_historical", "published_rank", "published_rank_of", "source",
                  "source_url", "published_at", "collected_at", "verified_at"]


class IncidentSerializer(serializers.ModelSerializer):
    country = serializers.CharField(source="country.slug")
    type = serializers.CharField(source="incident_type.name")
    category = serializers.CharField(source="incident_type.category.slug")
    sources = serializers.SerializerMethodField()

    class Meta:
        model = Incident
        fields = ["id", "country", "type", "category", "title", "description", "event_date", "event_date_precision",
                  "location", "victims_reported_min", "victims_reported_max", "victims_verified", "confidence",
                  "published_at", "sources"]

    def get_sources(self, obj):
        return [{"organisation": c.source.organisation, "url": c.source_url, "reported_number": c.reported_number,
                 "published_at": c.published_at} for c in obj.claims.exclude(status="rejected").select_related("source")]


class ScoreSerializer(serializers.ModelSerializer):
    country = CountrySerializer()
    category = serializers.CharField(source="category.slug", default=None)
    position_change = serializers.IntegerField(read_only=True)

    class Meta:
        model = CountryScore
        fields = ["country", "category", "score", "rank", "previous_rank", "position_change", "coverage", "confidence",
                  "is_ranked", "status_label", "imputed_categories"]


class SnapshotSerializer(serializers.ModelSerializer):
    methodology = serializers.SerializerMethodField()
    reporting_period = serializers.CharField(source="reporting_period.slug")

    class Meta:
        model = RankingSnapshot
        fields = ["id", "reporting_period", "status", "calculated_at", "published_at", "effective_weights",
                  "overall_available", "unavailable_reason", "methodology"]

    def get_methodology(self, s):
        m = s.methodology
        return {"name": m.name, "version": m.version, "mode": m.mode, "min_coverage": m.min_coverage,
                "description": m.description, "limitations": m.limitations}


class ReportSerializer(serializers.ModelSerializer):
    country = serializers.CharField(source="country.slug")
    pdf_url = serializers.SerializerMethodField()

    class Meta:
        model = CountryReport
        fields = ["id", "title", "country", "version", "published_at", "pdf_url"]

    def get_pdf_url(self, r):
        req = self.context.get("request")
        return req.build_absolute_uri(f"/reports/{r.pk}.pdf") if req else f"/reports/{r.pk}.pdf"
