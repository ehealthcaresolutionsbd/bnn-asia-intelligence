"""Platform test-suite. Uses synthetic fixtures inside the test database only – never production data."""
import datetime as dt

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.catalog.models import CategoryVersion, Indicator, IntelligenceCategory
from apps.core.models import AuditLog, Country, ReportingPeriod
from apps.incidents.models import Incident, IncidentClaim, IncidentType
from apps.observations.models import IndicatorObservation
from apps.rankings.engine import calculate, effective_weights, publish
from apps.rankings.models import MethodologyWeight, RankingMethodology
from apps.sources.connectors.base import Connector
from apps.sources.models import DataSource

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}


@override_settings(CACHES=LOCMEM)
class PlatformTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_platform", verbosity=0)
        IntelligenceCategory.objects.filter(slug="freedom-democracy").update(is_enabled=False)  # tests cover a disabled category
        cls.period = ReportingPeriod.objects.get(slug="2026")
        cls.src = DataSource.objects.get(slug="wb-wgi")
        cls.m = RankingMethodology.objects.get(version="1.0.0")
        cls.cats = {c.slug: c for c in IntelligenceCategory.objects.all()}
        cls.a, cls.b, cls.c = (Country.objects.get(iso3=x) for x in ("BGD", "IND", "NPL"))

    def obs(self, country, code, value, year=2026, verified=True, historical=False):
        return IndicatorObservation.objects.create(
            indicator=Indicator.objects.get(code=code), country=country, reporting_period=self.period, value=value,
            reference_start=dt.date(year, 1, 1), reference_end=dt.date(year, 12, 31), reference_label=f"T{year}{code}",
            source=self.src, source_url="https://example.org", collected_at=timezone.now(), is_historical=historical,
            verification_status="verified" if verified else "pending")

    def only(self, *slugs):
        """Restrict the methodology to the given categories (weights equal)."""
        self.m.weights.all().delete()
        for s in slugs:
            MethodologyWeight.objects.create(methodology=self.m, category=self.cats[s], weight=100 / len(slugs))
        for c in IntelligenceCategory.objects.all():
            c.is_enabled = c.scoring_enabled = c.ranking_included = True
            c.save()


class CategoryTests(PlatformTestCase):
    def test_disabling_category_keeps_data_and_versions(self):
        self.obs(self.a, "wgi_ge", 1.0)
        cat = self.cats["good-governance"]
        v = cat.version
        cat.is_enabled = False
        cat.save()
        self.assertEqual(IndicatorObservation.objects.filter(indicator__category=cat).count(), 1)
        self.assertEqual(cat.version, v + 1)
        self.assertTrue(CategoryVersion.objects.filter(category=cat, version=v + 1).exists())
        self.assertFalse(cat.ranked)
        cat.is_enabled = True
        cat.save()
        self.assertTrue(IntelligenceCategory.objects.get(pk=cat.pk).ranked)

    def test_seed_activates_freedom_democracy_once(self):
        fd = IntelligenceCategory.objects.filter(slug="freedom-democracy")
        RankingMethodology.objects.filter(version="2.1.0").delete()
        fd.update(is_enabled=False, activation_date=None)
        call_command("seed_platform", verbosity=0)
        self.assertTrue(fd.get().is_enabled)                      # v2.1.0 activates it
        fd.update(is_enabled=False)                               # an admin switches it off again
        RankingMethodology.objects.filter(version="2.1.0").delete()
        call_command("seed_platform", verbosity=0)
        self.assertFalse(fd.get().is_enabled)                     # never overridden
        self.assertFalse(self.cats["freedom-democracy"].is_enabled)
        self.assertTrue(all(self.cats[s].is_enabled for s in ["good-governance", "human-rights", "press-freedom",
                                                              "rule-of-law", "economic-social"]))


class WeightModeTests(PlatformTestCase):
    def test_auto_reweights_when_category_disabled(self):
        w, ok, _ = effective_weights(self.m)  # freedom-democracy (20) disabled → 80 remaining
        self.assertTrue(ok)
        self.assertAlmostEqual(sum(w.values()), 1.0)
        self.assertAlmostEqual(w[self.cats["good-governance"].id], 25 / 80)
        self.assertNotIn(self.cats["freedom-democracy"].id, w)

    def test_strict_makes_overall_unavailable(self):
        self.m.mode = "strict"
        self.m.save()
        w, ok, reason = effective_weights(self.m)
        self.assertFalse(ok)
        self.assertIn("Freedom & Democracy", reason)
        snap = calculate(self.m)
        self.assertFalse(snap.overall_available)
        self.assertFalse(snap.scores.filter(category=None, is_ranked=True).exists())

    def test_custom_requires_100(self):
        self.m.mode = "custom"
        self.m.save()
        _, ok, reason = effective_weights(self.m)   # active weights sum to 80
        self.assertFalse(ok)
        self.assertIn("80.0%", reason)


class ScoringTests(PlatformTestCase):
    def test_insufficient_data_not_ranked_and_missing_not_zero(self):
        self.only("good-governance", "rule-of-law")
        for code in ("wgi_ge", "wgi_rq", "wgi_cc"):
            self.obs(self.a, code, 0.5)
            self.obs(self.b, code, -0.5)
        self.obs(self.a, "wgi_rl", 0.5)
        self.obs(self.b, "wgi_rl", -0.5)
        # Rule of law needs 50% indicator weight: wgi_rl(1) of 2.5 total = 40% → category missing → coverage 50% < 60%
        snap = calculate(self.m)
        overall = snap.scores.get(country=self.a, category=None)
        self.assertFalse(overall.is_ranked)
        self.assertEqual(overall.status_label, "Not Ranked – Insufficient Data")
        self.assertIsNone(overall.score)
        self.assertFalse(snap.scores.filter(country=self.c, score=0).exists())  # NPL has no data – never 0

    def test_missing_category_cannot_improve_score(self):
        self.only("good-governance", "economic-social")
        self.m.min_coverage = 0.4
        self.m.save()
        for code in ("wgi_ge", "wgi_rq", "wgi_cc"):
            self.obs(self.a, code, -2.0)     # very poor governance
            self.obs(self.b, code, 2.0)
        self.obs(self.b, "imf_gdp_growth", -10)  # B has terrible economics → econ score 0
        self.obs(self.b, "imf_inflation", 30)
        self.obs(self.b, "imf_unemployment", 25)
        self.obs(self.c, "imf_gdp_growth", 10)
        self.obs(self.c, "imf_inflation", 0)
        self.obs(self.c, "imf_unemployment", 0)
        snap = calculate(self.m)
        a = snap.scores.get(country=self.a, category=None)
        gov_a = snap.scores.get(country=self.a, category=self.cats["good-governance"]).score
        # A has no economic data: imputed value must be <= its own governance mean, so overall <= gov score
        self.assertTrue(a.is_ranked)
        self.assertLessEqual(a.score, gov_a + 1e-9)
        self.assertIn(self.cats["economic-social"].id, a.imputed_categories)
        self.assertNotEqual(a.confidence, "high")

    def test_unverified_and_historical_excluded(self):
        self.only("good-governance")
        self.obs(self.a, "wgi_ge", 2.5, verified=False)
        self.obs(self.b, "wgi_ge", 2.5, year=2024, historical=True)
        snap = calculate(self.m)
        self.assertFalse(snap.scores.filter(category=self.cats["good-governance"], is_ranked=True).exists())

    def test_ties_share_rank_and_published_snapshot_frozen(self):
        self.only("good-governance")
        self.m.min_coverage = 0.1
        self.m.save()
        for c in (self.a, self.b):
            for code in ("wgi_ge", "wgi_rq", "wgi_cc"):
                self.obs(c, code, 1.0)
        snap = calculate(self.m)
        ranks = set(snap.scores.filter(category=None, is_ranked=True).values_list("rank", flat=True))
        self.assertEqual(ranks, {1})
        publish(snap)
        with self.assertRaises(ValidationError):
            snap.delete()
        self.m.refresh_from_db()
        self.assertTrue(self.m.is_published)
        with self.assertRaises(ValidationError):
            self.m.min_coverage = 0.9
            self.m.save()


class IncidentTests(PlatformTestCase):
    def setUp(self):
        self.t = IncidentType.objects.get(slug="journalist-arrest")
        self.u1 = User.objects.create_user("r1", password="x" * 12)
        self.u2 = User.objects.create_user("r2", password="x" * 12)

    def inc(self, **kw):
        d = dict(country=self.a, incident_type=self.t, reporting_period=self.period, title="t", description="d",
                 event_date=dt.date(2026, 3, 1), created_by=self.u1)
        d.update(kw)
        return Incident(**d)

    def test_2025_event_rejected_from_2026(self):
        i = self.inc(event_date=dt.date(2025, 12, 30))
        with self.assertRaises(ValidationError):
            i.full_clean()

    def test_sensitive_needs_second_person(self):
        i = self.inc(verification_status="verified", is_published=True, approved_by=self.u1)
        with self.assertRaises(ValidationError):
            i.full_clean()
        i.approved_by = self.u2
        i.full_clean()

    def test_unverified_cannot_publish(self):
        i = self.inc(is_published=True, approved_by=self.u2)
        with self.assertRaises(ValidationError):
            i.full_clean()

    def test_conflicting_numbers_preserved(self):
        i = self.inc()
        i.save()
        for url, n in (("https://a.example/1", 3), ("https://b.example/2", 7)):
            IncidentClaim.objects.create(incident=i, source=self.src, source_url=url, claim_text="x", reported_number=n,
                                         collected_at=timezone.now())
        i.refresh_reported_range()
        self.assertEqual((i.victims_reported_min, i.victims_reported_max), (3, 7))
        self.assertEqual(i.claims.count(), 2)

    def test_aggregation_missing_vs_zero(self):
        from apps.core.management.commands.seed_platform import INCIDENT_INDICATOR_MAP
        from apps.incidents.services import aggregate_incidents
        self.inc(verification_status="verified").save()
        self.inc(verification_status="pending").save()
        self.inc(verification_status="verified", event_date=dt.date(2026, 4, 1),
                 duplicate_of=Incident.objects.first()).save()
        Country.objects.filter(pk=self.b.pk).update(incident_monitoring=True)
        aggregate_incidents(self.period, INCIDENT_INDICATOR_MAP)
        q = IndicatorObservation.objects.filter(indicator__code="bnn_journalists_detained")
        self.assertEqual(q.get(country=self.a).value, 1)        # duplicate + pending not counted
        self.assertEqual(q.get(country=self.b).value, 0)        # monitored → true zero
        self.assertFalse(q.filter(country=self.c).exists())     # not monitored → missing, not zero


class EditionRuleTests(PlatformTestCase):
    def test_counts_for(self):
        f = Connector.counts_for
        p = self.period
        self.assertEqual(f(None, p, dt.date(2026, 1, 1), dt.date(2026, 12, 31))[0], True)
        self.assertEqual(f(None, p, dt.date(2025, 1, 1), dt.date(2025, 12, 31))[0], False)
        ok, note = f(None, p, dt.date(2025, 1, 1), dt.date(2025, 12, 31), dt.date(2026, 2, 10))
        self.assertTrue(ok)
        self.assertIn("describes 2025", note)


class ApiTests(PlatformTestCase):
    def setUp(self):
        self.api = APIClient()

    def test_hidden_category_and_unverified_not_exposed(self):
        self.obs(self.a, "wgi_ge", 1.0)
        self.obs(self.a, "wgi_rq", 1.0, verified=False)
        self.obs(self.a, "wgi_va", 1.0)  # freedom-democracy disabled
        r = self.api.get(f"/api/v1/countries/{self.a.slug}/profile/").json()
        codes = {o["indicator"] for o in r["observations"]}
        self.assertEqual(codes, {"wgi_ge"})
        self.assertNotIn("freedom-democracy", {c["slug"] for c in r["categories"]})

    def test_ranking_unpublished(self):
        calculate(self.m)  # draft only
        r = self.api.get("/api/v1/ranking/").json()
        self.assertFalse(r["available"])

    def test_official_rankings_label(self):
        self.obs(self.a, "wgi_ge", 1.0)
        r = self.api.get("/api/v1/official-rankings/?indicator=wgi_ge").json()
        self.assertIn("not an official ranking", r["note"])
        self.assertEqual(r["results"][0]["bnn_asia_position"], 1)

    def test_write_blocked_for_anonymous(self):
        self.assertIn(self.api.post("/api/v1/countries/", {}).status_code, (401, 403, 405))

    def test_api_key(self):
        from apps.api.models import ApiClient
        _, key = ApiClient.issue("wp")
        self.assertEqual(self.api.get("/api/v1/config/", HTTP_AUTHORIZATION=f"Api-Key {key}").status_code, 200)
        self.assertEqual(self.api.get("/api/v1/config/", HTTP_AUTHORIZATION="Api-Key wrong").status_code, 401)


class AuditTests(PlatformTestCase):
    def test_changes_logged_and_immutable(self):
        cat = self.cats["press-freedom"]
        cat.public_visible = False
        cat.save()
        log = AuditLog.objects.filter(model="catalog.IntelligenceCategory", object_id=str(cat.pk), action="update").first()
        self.assertIsNotNone(log)
        self.assertIn("public_visible", log.changes)
        with self.assertRaises(ValidationError):
            log.delete()


class ReportTests(PlatformTestCase):
    def test_report_only_uses_verified_records(self):
        from apps.reports.builder import build_report
        self.obs(self.a, "wgi_ge", 0.7)
        self.obs(self.a, "wgi_rq", 0.9, verified=False)
        r = build_report(self.a, self.period)
        txt = r.sections["good-governance"]["text"]
        self.assertIn("Government Effectiveness", txt)
        self.assertNotIn("Regulatory Quality", txt)
        self.assertEqual(len(r.sections["good-governance"]["citations"]), 1)
