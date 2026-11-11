"""Report tests – synthetic data inside the test database only."""
import datetime as dt
import io
import re
import shutil
import statistics
import tempfile
from collections import defaultdict
from pathlib import Path

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.catalog.models import IntelligenceCategory
from apps.core.models import Country, ReportingPeriod
from apps.rankings.models import CountryScore, RankingMethodology, RankingSnapshot
from apps.signals.models import CountryVolumeDaily, SignalDaily

from .builder import MIN_COUNTRIES_Z, build_report
from .models import CountryReport

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
MEDIA = tempfile.mkdtemp(prefix="bnn-report-tests-")
ISO = ["BGD", "IND", "NPL", "PAK", "LKA", "BTN"]
DAYS = [dt.date(2026, m, d) for m in range(1, 7) for d in (3, 12, 21)]


def protests_for(iso, day):
    # BGD: rising protest activity; others flat
    return 4 * day.month if iso == "BGD" else 2 + ISO.index(iso) % 2


def media_for(iso, day):
    return 1 + (day.day % 2) if iso != "BTN" else 0


@override_settings(CACHES=LOCMEM, MEDIA_ROOT=MEDIA)
class ReportTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_platform", verbosity=0)
        cls.period = ReportingPeriod.objects.get(slug="2026")
        cls.countries = {iso: Country.objects.get(iso3=iso) for iso in ISO}
        cls.bgd = cls.countries["BGD"]
        Country.objects.exclude(iso3__in=ISO).update(is_active=False)
        vol, sig = [], []
        for iso, c in cls.countries.items():
            for d in DAYS:
                vol.append(CountryVolumeDaily(country=c, day=d, events=1000 + 10 * ISO.index(iso), articles=3000))
                p = protests_for(iso, d)
                sig.append(SignalDaily(country=c, day=d, signal="protests", events=p, mentions=p * 3, sources=p, articles=p * 2,
                                       sample_urls=[f"https://news.example.org/{iso}/{d:%Y%m%d}/{i}" for i in range(2)]))
                m = media_for(iso, d)
                if m:
                    sig.append(SignalDaily(country=c, day=d, signal="media_repression", events=m, mentions=m, sources=m,
                                           articles=m))
        CountryVolumeDaily.objects.bulk_create(vol)
        SignalDaily.objects.bulk_create(sig)
        cls.staff = User.objects.create_user("editor", password="x", is_staff=True, is_superuser=True)

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def make_snapshot(self):
        m = RankingMethodology.objects.get(version="1.0.0")
        snap = RankingSnapshot.objects.create(methodology=m, reporting_period=self.period, status="published",
                                              calculated_at=timezone.now(), published_at=timezone.now())
        cats = list(IntelligenceCategory.objects.filter(is_enabled=True, pdf_included=True)[:3])
        for i, (iso, c) in enumerate(self.countries.items()):
            score = 30.0 + 8 * i
            CountryScore.objects.create(snapshot=snap, country=c, category=None, score=score, rank=len(ISO) - i,
                                        coverage=0.8, confidence="medium", is_ranked=True,
                                        detail={"score_ci": [score - 3, score + 3], "rank_interval": [max(1, len(ISO) - i - 1), len(ISO) - i]})
            for j, cat in enumerate(cats):
                CountryScore.objects.create(snapshot=snap, country=c, category=cat, score=20.0 + 10 * i + j, rank=len(ISO) - i,
                                            coverage=1.0, confidence="high", is_ranked=True)
        return snap


class BuilderTests(ReportTestBase):
    def test_builds_without_snapshot_and_is_published(self):
        r = build_report(self.bgd, self.period)
        self.assertEqual(r.status, "published")
        self.assertIsNotNone(r.published_at)
        self.assertIsNone(r.snapshot)
        self.assertIn("not ranked", r.sections["executive_summary"]["text"])
        self.assertIn("insufficient data", r.sections["executive_summary"]["text"])
        ev = r.sections["event_data"]
        self.assertEqual(ev["data"]["volume"], 1000 * len(DAYS))
        protests = next(s for s in ev["signals"] if s["key"] == "protests")
        self.assertEqual(protests["events"], sum(protests_for("BGD", d) for d in DAYS))
        self.assertEqual(protests["peak_month"], "June 2026")
        self.assertGreater(protests["half_change"], 0)
        self.assertLessEqual(len(ev["evidence"]), 5)
        self.assertTrue(ev["evidence"][0]["url"].startswith("https://news.example.org/BGD/"))
        self.assertIn("Limitations of event data", r.sections["methodology"]["text"])
        self.assertTrue(1 <= len(r.sections["findings"]["items"]) <= 6)
        # every section id in _meta.order exists and is rendered in order
        keys = [k for k, _ in r.ordered_sections()]
        self.assertEqual(keys[:2], ["executive_summary", "findings"])

    def test_findings_only_contain_numbers_present_in_the_data(self):
        r = build_report(self.bgd, self.period)
        # independent recomputation from the raw rows
        vol = defaultdict(int)
        for v in CountryVolumeDaily.objects.all():
            vol[v.country.iso3] += v.events
        allowed = {"1,000", "2026"}
        for key in ("protests", "media_repression"):
            tot = defaultdict(int)
            for s in SignalDaily.objects.filter(signal=key):
                tot[s.country.iso3] += s.events
            rates = {iso: tot[iso] / vol[iso] * 1000 for iso in ISO}
            med = statistics.median(rates.values())
            z = (rates["BGD"] - statistics.mean(rates.values())) / statistics.stdev(rates.values())
            allowed |= {f"{rates['BGD']:.2f}", f"{med:.2f}", f"{z:+.1f}", str(len(ISO))}
            if med:
                allowed.add(f"{rates['BGD'] / med:.1f}")
            mid = DAYS[0] + (DAYS[-1] - DAYS[0]) / 2
            h = [[0, 0], [0, 0]]
            for s in SignalDaily.objects.filter(signal=key, country=self.bgd):
                h[0 if s.day <= mid else 1][0] += s.events
            for v in CountryVolumeDaily.objects.filter(country=self.bgd):
                h[0 if v.day <= mid else 1][1] += v.events
            r1, r2 = h[0][0] / h[0][1] * 1000, h[1][0] / h[1][1] * 1000
            allowed |= {f"{r1:.2f}", f"{r2:.2f}"}
            if r1:
                allowed.add(f"{(r2 - r1) / r1 * 100:+.0f}")
        items = r.sections["findings"]["items"]
        self.assertTrue(items)
        for item in items:
            nums = re.findall(r"[+-]?\d[\d,]*(?:\.\d+)?", item["text"])
            for n in nums:
                self.assertIn(n, allowed, f"{n!r} in finding {item['text']!r} is not derived from the data")
            self.assertTrue(r.sections["findings"]["citations"][item["citation"] - 1]["type"])
        self.assertGreaterEqual(len(ISO), MIN_COUNTRIES_Z)
        self.assertTrue(any("z-score" in i["text"] for i in items))

    def test_charts_created_with_snapshot(self):
        snap = self.make_snapshot()
        r = build_report(self.bgd, self.period)
        self.assertEqual(r.snapshot, snap)
        self.assertEqual(len(r.charts), 3)
        for ch in r.charts:
            self.assertTrue(ch["path"].startswith("reports/charts/"))
            self.assertTrue((Path(MEDIA) / ch["path"]).is_file())
            self.assertTrue(ch["alt"])
        es = r.sections["executive_summary"]
        self.assertIn("ranks 6 of 6", es["text"])
        self.assertIn("27.0–33.0", es["text"])       # score_ci from the statistics engine
        self.assertIn("plausible rank range is 5–6", es["text"])
        cat = next(s for _, s in r.ordered_sections() if s.get("kind") == "category" and s["data"]["score"] is not None)
        self.assertEqual(cat["data"]["median"], statistics.median([20.0 + 10 * i for i in range(6)]))
        self.assertIn("below the median", cat["text"])

    def test_locked_report_is_not_regenerated(self):
        r1 = build_report(self.bgd, self.period)
        r1.locked = True
        r1.save()
        r2 = build_report(self.bgd, self.period)
        self.assertEqual(r2.pk, r1.pk)
        self.assertTrue(r2.skipped_locked)
        self.assertEqual(CountryReport.objects.filter(country=self.bgd).count(), 1)

    def test_versioning_keeps_older_versions(self):
        self.make_snapshot()
        r1 = build_report(self.bgd, self.period)
        r2 = build_report(self.bgd, self.period)
        r1.refresh_from_db()
        self.assertEqual((r1.version, r2.version), (1, 2))
        self.assertEqual(r1.status, "superseded")
        self.assertEqual(r2.status, "published")
        self.assertNotEqual(r1.charts[0]["path"], r2.charts[0]["path"])
        self.assertTrue((Path(MEDIA) / r1.charts[0]["path"]).is_file())
        draft = build_report(self.bgd, self.period, publish=False)
        r2.refresh_from_db()
        self.assertEqual((draft.version, draft.status, r2.status), (3, "draft", "published"))

    def test_management_command(self):
        out = io.StringIO()
        call_command("generate_reports", country="bgd", no_publish=True, stdout=out)
        self.assertEqual(CountryReport.objects.get(country=self.bgd).status, "draft")
        call_command("generate_reports", stdout=out)
        self.assertEqual(CountryReport.objects.filter(status="published").count(), len(ISO))
        CountryReport.objects.filter(country=self.bgd).update(locked=True)
        call_command("generate_reports", stdout=out)
        self.assertIn("skipped – v2 is locked", out.getvalue())
        self.assertIn("1 skipped", out.getvalue())


class ViewTests(ReportTestBase):
    def test_pdf_view_returns_pdf_for_published_report(self):
        self.make_snapshot()
        r = build_report(self.bgd, self.period)
        resp = self.client.get(f"/reports/{r.pk}.pdf")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")
        self.assertTrue(resp.content.startswith(b"%PDF"))

    def test_html_view_hides_drafts_from_anonymous_users(self):
        draft = build_report(self.bgd, self.period, publish=False)
        self.assertEqual(self.client.get(f"/reports/{draft.pk}/").status_code, 404)
        self.assertEqual(self.client.get(f"/reports/{draft.pk}.pdf").status_code, 404)
        self.client.force_login(self.staff)
        resp = self.client.get(f"/reports/{draft.pk}/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "DRAFT")

    def test_html_view_and_chart_serving(self):
        self.make_snapshot()
        r = build_report(self.bgd, self.period)
        resp = self.client.get(f"/reports/{r.pk}/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Bangladesh")
        self.assertContains(resp, "Key Findings")
        self.assertNotContains(resp, "DRAFT – NOT FOR PUBLICATION")
        name = Path(r.charts[0]["path"]).name
        self.assertContains(resp, f"/reports/charts/{name}")
        img = self.client.get(f"/reports/charts/{name}")
        self.assertEqual(img.status_code, 200)
        self.assertEqual(img["Content-Type"], "image/png")
        self.assertEqual(self.client.get("/reports/charts/..%2F..%2Fsettings.png").status_code, 404)
        self.assertEqual(self.client.get("/reports/charts/missing.png").status_code, 404)

    def test_api_profile_lists_current_version_with_html_url(self):
        build_report(self.bgd, self.period)
        r2 = build_report(self.bgd, self.period)
        data = self.client.get(f"/api/v1/countries/{self.bgd.slug}/profile/?period=2026").json()
        self.assertEqual([x["id"] for x in data["reports"]], [r2.pk])
        self.assertTrue(data["reports"][0]["html_url"].endswith(f"/reports/{r2.pk}/"))

    @override_settings(STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
                                 "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
    def test_admin_edit_locks_report_and_regeneration_keeps_it(self):
        r = build_report(self.bgd, self.period)
        self.client.force_login(self.staff)
        url = f"/admin/reports/countryreport/{r.pk}/change/"
        page = self.client.get(url)
        self.assertEqual(page.status_code, 200)
        form = page.context["adminform"].form
        data = {"title": r.title, "status": r.status, "editor": ""}
        for name, field in form.fields.items():
            if name.startswith("section__"):
                data[name] = form.initial.get(name, field.initial) or ""
        data["section__executive_summary"] = "Edited by a BNN Asia editor."
        resp = self.client.post(url, data)
        self.assertEqual(resp.status_code, 302, getattr(resp, "context", None) and resp.context["adminform"].form.errors)
        r.refresh_from_db()
        self.assertTrue(r.locked)
        self.assertEqual(r.sections["executive_summary"]["text"], "Edited by a BNN Asia editor.")
        self.assertEqual(r.editor, self.staff)
        self.assertTrue(build_report(self.bgd, self.period).skipped_locked)
        self.client.post("/admin/reports/countryreport/", {"action": "unlock", "_selected_action": [r.pk]})
        r.refresh_from_db()
        self.assertFalse(r.locked)
        self.client.post("/admin/reports/countryreport/", {"action": "regenerate", "_selected_action": [r.pk]})
        self.assertEqual(CountryReport.objects.filter(country=self.bgd).count(), 2)
