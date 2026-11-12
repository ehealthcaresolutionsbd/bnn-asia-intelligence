"""Statistics layer tests: signal indicators, bootstrap CIs, log transform, Monte Carlo intervals, editorial
adjustments, auto-publish pipeline and open-data endpoints. Synthetic data inside the test database only."""
import csv
import datetime as dt
import io
import random
import time

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.catalog.models import Indicator, IntelligenceCategory
from apps.core.models import Country, ReportingPeriod
from apps.observations.models import IndicatorObservation
from apps.rankings.engine import _normalise, calculate, publish
from apps.rankings.models import MethodologyWeight, RankingMethodology, RankingSnapshot
from apps.signals.indicators import MIN_EVENTS, bootstrap_ratio_ci, build_signal_indicators
from apps.signals.models import CountryVolumeDaily, EditorialAdjustment, IngestedDay, SignalDaily
from apps.signals.pipeline import refresh_annual_index
from apps.sources.models import DataSource

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
TODAY = dt.date(2026, 6, 30)


@override_settings(CACHES=LOCMEM)
class IndexTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_platform", verbosity=0)
        IntelligenceCategory.objects.filter(slug="freedom-democracy").update(is_enabled=False)  # tests cover a disabled category
        cls.period = ReportingPeriod.objects.get(slug="2026")
        cls.v2 = RankingMethodology.objects.get(version="2.0.0")
        cls.cats = {c.slug: c for c in IntelligenceCategory.objects.all()}
        cls.a, cls.b, cls.c = (Country.objects.get(iso3=x) for x in ("BGD", "IND", "NPL"))
        cls.src = DataSource.objects.get(slug="bnn-signals")

    def feed(self, country, days, volume, signals, start=dt.date(2026, 1, 5)):
        """`days` consecutive days with `volume` events/day and {signal: events/day}."""
        for i in range(days):
            d = start + dt.timedelta(days=i)
            CountryVolumeDaily.objects.update_or_create(country=country, day=d,
                                                        defaults={"events": volume, "articles": volume * 2})
            for k, n in signals.items():
                SignalDaily.objects.update_or_create(country=country, day=d, signal=k,
                                                     defaults={"events": n(i) if callable(n) else n, "articles": 3})
            IngestedDay.objects.get_or_create(day=d, defaults={"source_url": "https://example.org/x.zip"})

    def obs(self, country, code, value, lo=None, hi=None):
        return IndicatorObservation.objects.create(
            indicator=Indicator.objects.get(code=code), country=country, reporting_period=self.period, value=value,
            ci_low=lo, ci_high=hi, reference_start=dt.date(2026, 1, 1), reference_end=dt.date(2026, 6, 30),
            reference_label="T", source=self.src, source_url="https://example.org", collected_at=timezone.now(),
            verification_status="verified")

    def only(self, *slugs, m=None):
        m = m or self.v2
        m.weights.all().delete()
        for s in slugs:
            MethodologyWeight.objects.create(methodology=m, category=self.cats[s], weight=100 / len(slugs))


class SeedTests(IndexTestCase):
    def test_seed_idempotent_v1_untouched_v2_created(self):
        v1 = RankingMethodology.objects.get(version="1.0.0")
        before = (v1.description, v1.updated_at, list(v1.weights.values_list("weight", flat=True)))
        call_command("seed_platform", verbosity=0)
        v1.refresh_from_db()
        self.assertEqual(before, (v1.description, v1.updated_at, list(v1.weights.values_list("weight", flat=True))))
        v2 = RankingMethodology.objects.get(version="2.0.0")
        self.assertEqual(v2.mode, "auto")
        self.assertEqual(sorted(v2.weights.values_list("weight", flat=True)), [5, 10, 15, 20, 25, 25])
        self.assertIn("bootstrap", v2.description)
        self.assertIn("ground truth", v2.limitations)
        self.assertTrue(RankingMethodology.objects.get(version="2.1.0").description.endswith("corrects this."))
        self.assertEqual(Indicator.objects.get(code="bnn_sig_violence").transform, "log")
        self.assertEqual(Indicator.objects.get(code="bnn_sig_protest_repression").transform, "none")
        self.assertEqual(DataSource.objects.filter(slug="bnn-signals").count(), 1)


class SignalIndicatorTests(IndexTestCase):
    def test_rates_and_missing(self):
        # 28 days (4 ISO weeks) × 100 events = 2,800 events; 5 media-repression/day → 50 per 1,000
        self.feed(self.a, 28, 100, {"media_repression": 5, "censorship": 1, "protests": 8, "protest_repression": 2,
                                    "killings_assaults": lambda i: i % 4})
        self.feed(self.c, 10, 20, {"media_repression": 5})          # 200 events < 300 → missing
        out = build_signal_indicators(self.period, today=TODAY)
        q = IndicatorObservation.objects.filter(source=self.src)
        mr = q.get(country=self.a, indicator__code="bnn_sig_media_repression")
        self.assertAlmostEqual(mr.value, 50.0)
        self.assertEqual(mr.sample_size, 2800)
        self.assertAlmostEqual(q.get(country=self.a, indicator__code="bnn_sig_censorship").value, 10.0)
        self.assertAlmostEqual(q.get(country=self.a, indicator__code="bnn_sig_protest_repression").value, 20.0)
        self.assertAlmostEqual(q.get(country=self.a, indicator__code="bnn_sig_arrests").value, 0.0)   # data → true zero
        viol = q.get(country=self.a, indicator__code="bnn_sig_violence")
        self.assertAlmostEqual(viol.value, 1000 * sum(i % 4 for i in range(28)) / 2800, places=5)
        self.assertLessEqual(viol.ci_low, viol.value)
        self.assertGreaterEqual(viol.ci_high, viol.value)
        self.assertLess(viol.ci_low, viol.ci_high)
        self.assertEqual(mr.data_status, "preliminary")
        self.assertEqual(mr.verification_status, "verified")
        self.assertEqual(mr.reference_start, dt.date(2026, 1, 1))
        self.assertEqual(mr.reference_end, dt.date(2026, 2, 1))
        self.assertEqual(mr.published_at, TODAY)
        self.assertTrue(mr.notes.startswith("Machine-computed aggregate of 2800 events from 5600 source articles; method v2"))
        self.assertFalse(q.filter(country=self.c).exists())
        self.assertFalse(q.filter(country=self.b).exists())
        self.assertGreater(out["written"], 0)
        self.assertEqual(MIN_EVENTS, 300)

    def test_reproducible_and_drops_below_threshold(self):
        self.feed(self.a, 30, 50, {"state_repression": lambda i: (i * 7) % 5})
        build_signal_indicators(self.period, today=TODAY)
        o1 = IndicatorObservation.objects.get(source=self.src, country=self.a, indicator__code="bnn_sig_state_repression")
        build_signal_indicators(self.period, today=TODAY)
        o2 = IndicatorObservation.objects.get(pk=o1.pk)
        self.assertEqual((o1.value, o1.ci_low, o1.ci_high), (o2.value, o2.ci_low, o2.ci_high))
        CountryVolumeDaily.objects.filter(country=self.a).update(events=5)       # 150 events → missing again
        build_signal_indicators(self.period, today=TODAY)
        self.assertFalse(IndicatorObservation.objects.filter(source=self.src, country=self.a).exists())

    def test_final_after_period(self):
        self.feed(self.a, 27, 100, {"censorship": 1}, start=dt.date(2026, 12, 4))   # ends 30 Dec
        build_signal_indicators(self.period, today=dt.date(2027, 1, 2))
        self.assertEqual(IndicatorObservation.objects.filter(source=self.src).first().data_status, "preliminary")
        self.feed(self.a, 1, 100, {"censorship": 1}, start=dt.date(2026, 12, 31))   # 31 Dec ingested → final
        build_signal_indicators(self.period, today=dt.date(2027, 1, 2))
        self.assertEqual(IndicatorObservation.objects.filter(source=self.src).first().data_status, "final")

    def test_too_few_weeks_is_missing(self):
        self.feed(self.a, 14, 500, {"censorship": 3})            # 7,000 events but only 2 weeks
        build_signal_indicators(self.period, today=TODAY)
        self.assertFalse(IndicatorObservation.objects.filter(source=self.src, country=self.a).exists())

    def test_bootstrap(self):
        num, den = [3, 0, 9, 1, 4, 12, 2, 0], [400, 380, 520, 300, 410, 600, 350, 390]
        lo, hi = bootstrap_ratio_ci(num, den, 1000, seed=7)
        point = 1000 * sum(num) / sum(den)
        self.assertLessEqual(lo, point)
        self.assertGreaterEqual(hi, point)
        self.assertLess(lo, hi)
        self.assertEqual((lo, hi), bootstrap_ratio_ci(num, den, 1000, seed=7))
        self.assertNotEqual((lo, hi), bootstrap_ratio_ci(num, den, 1000, seed=8))


class TransformTests(IndexTestCase):
    def test_log_transform(self):
        ind = Indicator.objects.get(code="bnn_sig_violence")
        out = _normalise(ind, {1: 0.0, 2: 9.0, 3: 99.0}, {})
        # log1p: 0, ln10, ln100 → evenly spaced; lower is better → 100, 50, 0
        self.assertAlmostEqual(out[1], 100.0)
        self.assertAlmostEqual(out[2], 50.0, places=3)
        self.assertAlmostEqual(out[3], 0.0)
        ind.transform = "none"
        self.assertAlmostEqual(_normalise(ind, {1: 0.0, 2: 9.0, 3: 99.0}, {})[2], 100 - 9 / 99 * 100, places=3)


class UncertaintyRankingTests(IndexTestCase):
    def setUp(self):
        self.only("press-freedom")
        self.v2.min_coverage = 0.5
        self.v2.save()
        self.countries = list(Country.objects.filter(is_active=True).order_by("iso3")[:8])
        for i, c in enumerate(self.countries):
            v = 5 + i * 3
            self.obs(c, "bnn_sig_media_repression", v, v - 1 - i % 3, v + 1 + i % 3)
            self.obs(c, "bnn_sig_censorship", 2 + i, 1.5 + i, 2.5 + i)
            self.obs(c, "wgi_va_pf", -0.5 + 0.1 * i)              # independent anchor (v2.2.0)

    def test_intervals_present_and_contain_point(self):
        snap = calculate(self.v2)
        rows = snap.scores.filter(category=None, is_ranked=True)
        self.assertEqual(rows.count(), 8)
        for r in rows:
            lo, hi = r.detail["score_ci"]
            best, worst = r.detail["rank_interval"]
            self.assertLessEqual(lo, r.score)
            self.assertGreaterEqual(hi, r.score)
            self.assertLessEqual(best, r.rank)
            self.assertLessEqual(r.rank, worst)
            self.assertEqual(r.detail["editorial"], [])
        cat = snap.scores.get(category=self.cats["press-freedom"], country=self.countries[0])
        self.assertIn("score_ci", cat.detail)
        self.assertIn("bnn_sig_media_repression", cat.detail)
        self.assertEqual(len(cat.detail["bnn_sig_media_repression"]["ci"]), 2)
        # reproducible
        snap2 = calculate(self.v2)
        self.assertEqual([r.detail for r in snap.scores.order_by("country", "category")],
                         [r.detail for r in snap2.scores.order_by("country", "category")])
        # unranked countries have no intervals
        nr = snap.scores.filter(category=None, is_ranked=False).first()
        self.assertIsNone(nr.detail["score_ci"])
        self.assertIsNone(nr.detail["rank_interval"])

    def test_no_uncertainty_gives_point_intervals(self):
        IndicatorObservation.objects.update(ci_low=None, ci_high=None)
        snap = calculate(self.v2)
        for r in snap.scores.filter(category=None, is_ranked=True):
            self.assertAlmostEqual(r.detail["score_ci"][0], r.score, delta=0.02)
            self.assertAlmostEqual(r.detail["score_ci"][1], r.score, delta=0.02)
            self.assertEqual(r.detail["rank_interval"], [r.rank, r.rank])

    def test_editorial_override_exclude_note(self):
        a, b, c = self.countries[:3]
        base = calculate(self.v2)
        orig_b = base.scores.get(country=b, category=None).score
        orig_cat_a = base.scores.get(country=a, category=self.cats["press-freedom"]).score
        EditorialAdjustment.objects.create(reporting_period=self.period, country=b, kind="override", score=100,
                                           reason="Documented crackdown not captured")
        EditorialAdjustment.objects.create(reporting_period=self.period, country=c, kind="exclude",
                                           reason="Data blackout")
        EditorialAdjustment.objects.create(reporting_period=self.period, country=a, kind="note",
                                           category=self.cats["press-freedom"], reason="Election year")
        EditorialAdjustment.objects.create(reporting_period=self.period, country=a, kind="exclude", is_active=False,
                                           reason="inactive – ignored")
        snap = calculate(self.v2)
        sb = snap.scores.get(country=b, category=None)
        self.assertEqual(sb.score, 100)
        self.assertEqual(sb.rank, 1)                                 # ties share rank 1
        self.assertEqual(sb.detail["editorial"][0]["kind"], "override")
        self.assertEqual(sb.detail["editorial"][0]["original_score"], orig_b)
        self.assertEqual(sb.detail["score_ci"], [100, 100])
        sc = snap.scores.get(country=c, category=None)
        self.assertFalse(sc.is_ranked)
        self.assertIsNone(sc.rank)
        self.assertEqual(sc.status_label, "Excluded by editors")
        self.assertEqual(sc.detail["editorial"][0]["reason"], "Data blackout")
        ranks = sorted(snap.scores.filter(category=None, is_ranked=True).values_list("rank", flat=True))
        self.assertEqual(len(ranks), 7)
        self.assertEqual(ranks[-1], 7)                               # excluded country leaves no gap
        sa = snap.scores.get(country=a, category=self.cats["press-freedom"])
        self.assertEqual(sa.score, orig_cat_a)                       # note changes nothing
        self.assertEqual(sa.detail["editorial"], [{"kind": "note", "reason": "Election year",
                                                   "original_score": orig_cat_a}])
        self.assertTrue(snap.scores.get(country=a, category=None).is_ranked)   # inactive exclude ignored

    def test_category_override_feeds_overall(self):
        a = self.countries[0]
        EditorialAdjustment.objects.create(reporting_period=self.period, country=a, kind="override", score=0,
                                           category=self.cats["press-freedom"], reason="test")
        snap = calculate(self.v2)
        self.assertEqual(snap.scores.get(country=a, category=self.cats["press-freedom"]).score, 0)
        self.assertEqual(snap.scores.get(country=a, category=None).score, 0)


class PerformanceTests(IndexTestCase):
    def test_48_countries_25_indicators_under_20s(self):
        self.v2.min_coverage = 0.0
        self.v2.save()
        for c in IntelligenceCategory.objects.all():
            c.is_enabled = c.scoring_enabled = c.ranking_included = True
            c.save()
        rnd = random.Random(1)
        inds = list(Indicator.objects.filter(used_in_scoring=True))
        rows = []
        for c in Country.objects.filter(is_active=True):
            for ind in inds:
                v = rnd.uniform(0, 50)
                rows.append(IndicatorObservation(
                    indicator=ind, country=c, reporting_period=self.period, value=v, ci_low=v * 0.8, ci_high=v * 1.2,
                    reference_start=dt.date(2026, 1, 1), reference_end=dt.date(2026, 6, 30), reference_label="P",
                    source=self.src, source_url="https://example.org", collected_at=timezone.now(),
                    verification_status="verified"))
        IndicatorObservation.objects.bulk_create(rows)
        t = time.perf_counter()
        snap = calculate(self.v2)
        elapsed = time.perf_counter() - t
        print(f"\ncalculate() with Monte Carlo: {Country.objects.filter(is_active=True).count()} countries × "
              f"{len(inds)} indicators in {elapsed:.2f}s")
        self.assertLess(elapsed, 20)
        self.assertEqual(snap.scores.filter(category=None, is_ranked=True).count(),
                         Country.objects.filter(is_active=True).count())


class PipelineAndApiTests(IndexTestCase):
    def setUp(self):
        self.api = APIClient()
        for i, c in enumerate(Country.objects.filter(is_active=True).order_by("iso3")[:6]):
            self.feed(c, 28, 60 + 10 * i, {"media_repression": i + 1, "censorship": 1, "state_repression": i,
                                           "arrests_detentions": 2, "killings_assaults": lambda d: d % 3 + i,
                                           "protests": 5, "protest_repression": i % 3})
        # Overall needs ≥60 % of the active weight (80): human rights 25 + press freedom 10 + governance 25 = 75 %.
        for c in Country.objects.filter(is_active=True).order_by("iso3")[:6]:
            for code in ("wgi_ge", "wgi_rq", "wgi_cc", "wgi_va_hr", "wgi_va_pf"):
                IndicatorObservation.objects.create(
                    indicator=Indicator.objects.get(code=code), country=c, reporting_period=self.period, value=0.1,
                    reference_start=dt.date(2026, 1, 1), reference_end=dt.date(2026, 12, 31), reference_label="WGI",
                    source=DataSource.objects.get(slug="wb-wgi"), source_url="https://example.org",
                    collected_at=timezone.now(), verification_status="verified")

    def test_refresh_publishes_and_reuses_frozen_methodology(self):
        out = refresh_annual_index(self.period)
        self.assertEqual(out["status"], "published")
        self.assertEqual(out["ranked"], 6)
        self.assertTrue(RankingMethodology.objects.get(version="2.2.0").is_published)
        out2 = refresh_annual_index(self.period)                      # calculate() under a frozen methodology
        self.assertEqual(RankingSnapshot.objects.get(pk=out["snapshot"]).status, "superseded")
        self.assertEqual(RankingSnapshot.objects.get(pk=out2["snapshot"]).status, "published")
        snap = RankingSnapshot.objects.get(pk=out2["snapshot"])
        self.assertEqual(snap.scores.filter(category=None, previous_rank__isnull=False).count(), 6)
        self.assertEqual(RankingMethodology.objects.get(version="1.0.0").is_published, False)

    def test_command(self):
        call_command("refresh_index", "--no-publish", stdout=io.StringIO())
        self.assertEqual(RankingSnapshot.objects.get().status, "draft")

    def test_ranking_api_csv_and_methodology(self):
        r = self.api.get("/api/v1/methodology/").json()
        self.assertIsNone(r["methodology"])                           # nothing published yet
        refresh_annual_index(self.period)
        r = self.api.get("/api/v1/ranking/").json()
        row = r["results"][0]
        self.assertEqual(r["snapshot"]["methodology"]["version"], "2.2.0")
        self.assertEqual(len(row["score_ci"]), 2)
        self.assertLessEqual(row["rank_interval"][0], row["rank"])
        self.assertEqual(row["editorial"], [])

        p = self.api.get(f"/api/v1/countries/{Country.objects.order_by('iso3').first().slug}/profile/").json()
        sig = [o for o in p["observations"] if o["indicator"] == "bnn_sig_media_repression"][0]
        self.assertIsNotNone(sig["ci_low"])
        self.assertGreater(sig["sample_size"], 0)

        resp = self.api.get("/api/v1/ranking.csv")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp["Content-Type"].startswith("text/csv"))
        self.assertIn("attachment", resp["Content-Disposition"])
        rows = list(csv.DictReader(io.StringIO(b"".join(resp.streaming_content).decode())))
        self.assertEqual(len(rows), Country.objects.filter(is_active=True).count())
        self.assertEqual(rows[0]["rank"], "1")
        self.assertEqual(rows[0]["methodology_version"], "2.2.0")
        self.assertNotEqual(rows[0]["score_ci_low"], "")
        resp = self.api.get("/api/v1/ranking.csv?category=human-rights")
        rows = list(csv.DictReader(io.StringIO(b"".join(resp.streaming_content).decode())))
        self.assertEqual({r["category"] for r in rows}, {"human-rights"})
        self.assertEqual(self.api.get("/api/v1/ranking.csv?category=freedom-democracy").status_code, 404)

        m = self.api.get("/api/v1/methodology/").json()
        self.assertEqual(m["methodology"]["version"], "2.2.0")
        self.assertEqual(len(m["methodology"]["weights"]), 6)
        self.assertIn("limitations", m["methodology"])
        keys = {x["key"] for x in m["signals"]}
        self.assertIn("media_repression", keys)
        mr = [x for x in m["signals"] if x["key"] == "media_repression"][0]
        self.assertEqual(mr["cameo_prefixes"], ["17", "18", "19", "20"])
        self.assertIn("JRN", mr["target_types"])
        codes = {i["code"] for i in m["indicators"]}
        self.assertIn("bnn_sig_violence", codes)
        self.assertNotIn("bnn_sig_protest_repression", codes)          # freedom-democracy hidden
        self.assertEqual(m["data_volume"]["days_ingested"], 28)
        self.assertEqual(m["data_volume"]["events_in_countries"], sum(28 * (60 + 10 * i) for i in range(6)))
        self.assertIsNotNone(m["data_volume"]["last_update"])

    def test_csv_404_without_published(self):
        self.assertEqual(self.api.get("/api/v1/ranking.csv").status_code, 404)
