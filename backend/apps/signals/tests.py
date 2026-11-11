"""GDELT ingestion tests. Never touch the network: requests.get is mocked with a zip of tests_fixture.tsv.

tests_fixture.tsv = 300 real rows sampled from the GDELT 1.0 export of 2026-03-01 (BG/IN/PK with and without
signal matches, Gaza 'GZ' and West Bank 'WE', 30 Asian rows whose EVENT date is in 2025, and non-Asian rows).
"""
import csv
import io
import zipfile
from collections import Counter, defaultdict
from datetime import date
from io import StringIO
from pathlib import Path
from unittest import mock

import requests
from django.contrib import admin
from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import RequestFactory, SimpleTestCase, TestCase

from apps.core.models import Country, ReportingPeriod

from . import ingest, rules
from .models import CountryVolumeDaily, EditorialAdjustment, IngestedDay, SignalDaily

FIXTURE = Path(__file__).with_name("tests_fixture.tsv")
D1, D2 = date(2026, 3, 1), date(2026, 3, 2)


def fixture_rows():
    with open(FIXTURE, newline="", encoding="utf-8") as fh:
        return list(csv.reader(fh, delimiter="\t", quoting=csv.QUOTE_NONE))


def fixture_zip():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("20260301.export.CSV", FIXTURE.read_bytes())
    return buf.getvalue()


class FakeResponse:
    def __init__(self, status=200, body=b""):
        self.status_code, self.body = status, body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}")

    def iter_content(self, chunk_size=1):
        for i in range(0, len(self.body), chunk_size):
            yield self.body[i:i + chunk_size]


def ok_get(*a, **kw):
    return FakeResponse(200, fixture_zip())


def row(code="", a1="", a2="", geo="BG", sqldate="20260301"):
    r = [""] * 58
    r[rules.COL["event_code"]], r[rules.COL["a1type"]], r[rules.COL["a2type"]] = code, a1, a2
    r[rules.COL["geo_country"]], r[rules.COL["sqldate"]] = geo, sqldate
    return r


class ClassifyTests(SimpleTestCase):
    def k(self, *args):
        return set(ingest.classify(row(*args)))

    def test_known_cameo_codes(self):
        # 173 arrest by police of a journalist
        self.assertEqual(self.k("173", "COP", "JRN"), {"media_repression", "media_arrests", "arrests_detentions"})
        # 1823 killing, no actor types -> only the unconstrained rule
        self.assertEqual(self.k("1823"), {"killings_assaults"})
        # military kills civilians -> also state repression
        self.assertEqual(self.k("1823", "MIL", "CVL"), {"killings_assaults", "state_repression"})
        self.assertEqual(self.k("145"), {"protests"})
        # 1724 (impose curfew) by government; without a state perpetrator nothing matches
        self.assertEqual(self.k("1724", "GOV"), {"protest_repression", "censorship"})
        self.assertEqual(self.k("1724"), set())
        self.assertEqual(self.k("175", "COP", "OPP"), {"state_repression", "protest_repression"})
        self.assertEqual(self.k("0832"), {"rule_of_law_cooperation"})
        self.assertEqual(self.k("083"), set())          # prefix match is on the code, not the reverse
        self.assertEqual(self.k("010", "GOV", "MED"), set())
        self.assertEqual(self.k(""), set())

    def test_fips_mapping(self):
        cases = {"BG": "BGD", "IN": "IND", "PK": "PAK", "CE": "LKA", "BM": "MMR", "RP": "PHL", "GZ": "PSE",
                 "WE": "PSE", "US": None, "UK": None, "": None}
        for fips, iso3 in cases.items():
            self.assertEqual(ingest.country_iso3(row(geo=fips)), iso3, fips)


class IngestTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_platform", verbosity=0)
        cls.period = ReportingPeriod.objects.get(slug="2026")
        cls.iso3s = set(Country.objects.values_list("iso3", flat=True))

    def expected(self):
        """Independent re-computation of what the fixture should produce."""
        vol, sig = Counter(), defaultdict(Counter)
        for r in fixture_rows():
            iso = rules.FIPS_TO_ISO3.get(r[51])
            if iso not in self.iso3s or not r[1].startswith("2026"):
                continue
            vol[iso] += 1
            for k in ingest.classify(r):
                sig[(iso, k)]["events"] += 1
                sig[(iso, k)]["mentions"] += int(r[31])
                sig[(iso, k)]["articles"] += int(r[33])
        return vol, sig


class IngestTests(IngestTestCase):
    def test_all_seeded_countries_have_fips(self):
        self.assertEqual(len(self.iso3s), 48)
        self.assertEqual(self.iso3s - set(rules.ISO3_TO_FIPS), set())

    def test_aggregation_totals(self):
        with mock.patch.object(ingest.requests, "get", side_effect=ok_get) as get:
            r = ingest.ingest_day(D1, period=self.period)
        self.assertEqual(r.status, "ok")
        self.assertEqual(get.call_args.kwargs["headers"]["User-Agent"], "BNN-Asia-Intelligence/1.0 (+https://bnnasia.org; research@bnnasia.org)")
        self.assertIn("timeout", get.call_args.kwargs)
        rec = IngestedDay.objects.get(day=D1)
        self.assertEqual((rec.status, rec.rows_total), ("ok", 300))

        bgd = CountryVolumeDaily.objects.get(country__iso3="BGD", day=D1)
        self.assertEqual((bgd.events, bgd.articles), (70, 433))      # hand-checked against the fixture
        self.assertEqual(CountryVolumeDaily.objects.get(country__iso3="PSE", day=D1).events, 20)  # 10 GZ + 10 WE

        vol, sig = self.expected()
        got_vol = Counter()
        for o in CountryVolumeDaily.objects.select_related("country"):
            got_vol[o.country.iso3] += o.events
        self.assertEqual(got_vol, vol)
        self.assertEqual(rec.rows_asia, sum(vol.values()))
        got = {(o.country.iso3, o.signal): o for o in SignalDaily.objects.select_related("country")}
        self.assertEqual(set(got), set(sig))
        for key, exp in sig.items():
            o = got[key]
            self.assertEqual((o.events, o.mentions, o.articles), (exp["events"], exp["mentions"], exp["articles"]), key)
            self.assertLessEqual(len(o.sample_urls), 5)
            self.assertEqual(len(o.sample_urls), len(set(o.sample_urls)))
            self.assertTrue(o.sample_urls)

    def test_2025_events_not_counted(self):
        asia_2025 = sum(1 for r in fixture_rows()
                        if rules.FIPS_TO_ISO3.get(r[51]) in self.iso3s and r[1].startswith("2025"))
        self.assertEqual(asia_2025, 30)
        with mock.patch.object(ingest.requests, "get", side_effect=ok_get):
            ingest.ingest_day(D1, period=self.period)
        self.assertFalse(CountryVolumeDaily.objects.filter(day__lt=self.period.start_date).exists())
        self.assertFalse(SignalDaily.objects.filter(day__lt=self.period.start_date).exists())
        import json
        self.assertEqual(json.loads(IngestedDay.objects.get(day=D1).message)["rows_out_of_period"], asia_2025)
        # IND has 3 events dated 2025 in the fixture: they are not in its volume
        ind_2026 = sum(1 for r in fixture_rows() if r[51] == "IN" and r[1].startswith("2026"))
        self.assertEqual(CountryVolumeDaily.objects.get(country__iso3="IND").events, ind_2026)

    def test_idempotent_per_file_and_additive_across_files(self):
        with mock.patch.object(ingest.requests, "get", side_effect=ok_get) as get:
            self.assertEqual(ingest.ingest_day(D1, period=self.period).status, "ok")
            self.assertEqual(ingest.ingest_day(D1, period=self.period).status, "skipped")
            self.assertEqual(get.call_count, 1)              # second run does not even download
            with self.assertRaises(ingest.AlreadyIngested):
                ingest.ingest_day(D1, period=self.period, force=True)
            self.assertEqual(CountryVolumeDaily.objects.get(country__iso3="BGD", day=D1).events, 70)
            # another FILE mentioning events of the same event day adds to the same rows
            self.assertEqual(ingest.ingest_day(D2, period=self.period).status, "ok")
        self.assertEqual(CountryVolumeDaily.objects.get(country__iso3="BGD", day=D1).events, 140)
        _, sig = self.expected()
        for o in SignalDaily.objects.select_related("country"):
            self.assertEqual(o.events, 2 * sig[(o.country.iso3, o.signal)]["events"])
            self.assertLessEqual(len(o.sample_urls), 5)
            self.assertEqual(len(o.sample_urls), len(set(o.sample_urls)))

    def test_missing_upstream_file(self):
        with mock.patch.object(ingest.requests, "get", return_value=FakeResponse(404)) as get:
            r = ingest.ingest_day(D1, period=self.period)
            self.assertEqual(r.status, "missing")
            self.assertEqual(IngestedDay.objects.get(day=D1).status, "missing")
            self.assertFalse(CountryVolumeDaily.objects.exists())
            self.assertEqual(ingest.ingest_day(D1, period=self.period).status, "skipped")
            self.assertEqual(get.call_count, 1)
        with mock.patch.object(ingest.requests, "get", side_effect=ok_get):
            self.assertEqual(ingest.ingest_day(D1, period=self.period, force=True).status, "ok")
        self.assertEqual(IngestedDay.objects.get(day=D1).status, "ok")

    def test_failure_recorded_then_retried(self):
        with mock.patch.object(ingest.requests, "get", side_effect=requests.ConnectionError("boom")):
            r = ingest.ingest_day(D1, period=self.period)
        self.assertEqual(r.status, "failed")
        self.assertIn("boom", IngestedDay.objects.get(day=D1).message)
        with mock.patch.object(ingest.requests, "get", return_value=FakeResponse(500)):
            self.assertEqual(ingest.ingest_day(D1, period=self.period).status, "failed")
        with mock.patch.object(ingest.requests, "get", side_effect=ok_get):
            self.assertEqual(ingest.ingest_day(D1, period=self.period).status, "ok")
        self.assertEqual(CountryVolumeDaily.objects.get(country__iso3="BGD", day=D1).events, 70)

    def test_failure_never_downgrades_ok(self):
        with mock.patch.object(ingest.requests, "get", side_effect=ok_get):
            ingest.ingest_day(D1, period=self.period)
        ingest.record_status(D1, "failed", "late error", ingest.export_url(D1))
        self.assertEqual(IngestedDay.objects.get(day=D1).status, "ok")

    def test_reset_period(self):
        with mock.patch.object(ingest.requests, "get", side_effect=ok_get):
            ingest.ingest_day(D1, period=self.period)
        ingest.reset_period(self.period)
        self.assertFalse(CountryVolumeDaily.objects.exists() or SignalDaily.objects.exists()
                         or IngestedDay.objects.exists())


class CommandAndTaskTests(IngestTestCase):
    def test_command_continues_on_missing_and_failed_days(self):
        def get(url, **kw):
            if "20260302" in url:
                return FakeResponse(404)
            if "20260303" in url:
                raise requests.ConnectionError("down")
            return ok_get()

        for workers in ("1", "3"):
            IngestedDay.objects.all().delete()
            CountryVolumeDaily.objects.all().delete()
            SignalDaily.objects.all().delete()
            out = StringIO()
            with mock.patch.object(ingest.requests, "get", side_effect=get), \
                    mock.patch.object(ingest.requests.Session, "get", side_effect=lambda s, url, **kw: get(url, **kw),
                                      autospec=True):
                call_command("ingest_gdelt", "--start", "2026-03-01", "--end", "2026-03-04", "--workers", workers,
                             stdout=out)
            st = dict(IngestedDay.objects.values_list("day", "status"))
            self.assertEqual(st, {D1: "ok", D2: "missing", date(2026, 3, 3): "failed", date(2026, 3, 4): "ok"}, workers)
            self.assertEqual(CountryVolumeDaily.objects.get(country__iso3="BGD", day=D1).events, 140)
            self.assertIn("Done", out.getvalue())

        # re-run: ok and missing days are skipped, only the failed day is retried
        with mock.patch.object(ingest.requests, "get", side_effect=ok_get) as g:
            call_command("ingest_gdelt", "--start", "2026-03-01", "--end", "2026-03-04", stdout=StringIO())
        self.assertEqual(g.call_count, 1)
        self.assertEqual(CountryVolumeDaily.objects.get(country__iso3="BGD", day=D1).events, 210)

    def test_command_reset_requires_period_start(self):
        from django.core.management.base import CommandError
        with self.assertRaises(CommandError):
            call_command("ingest_gdelt", "--start", "2026-03-01", "--end", "2026-03-01", "--reset", stdout=StringIO())

    def test_ingest_yesterday_task(self):
        from . import tasks
        with mock.patch.object(tasks, "ingest_day",
                               return_value=ingest.IngestResult(D1, "ok", None, 1.0, "")) as m:
            res = tasks.ingest_yesterday()
        self.assertEqual(res["status"], "ok")
        from datetime import datetime, timedelta, timezone
        m.assert_called_once_with(datetime.now(timezone.utc).date() - timedelta(days=1))

    def test_beat_schedule(self):
        from django.conf import settings
        self.assertEqual(settings.CELERY_BEAT_SCHEDULE["ingest-gdelt-daily"]["task"], "apps.signals.tasks.ingest_yesterday")


class AdminTests(IngestTestCase):
    def test_registered_and_created_by(self):
        for m in (IngestedDay, SignalDaily, CountryVolumeDaily, EditorialAdjustment):
            self.assertTrue(admin.site.is_registered(m))
        ma = admin.site._registry[EditorialAdjustment]
        user = User.objects.create_superuser("ed", "ed@example.org", "x")
        req = RequestFactory().post("/")
        req.user = user
        obj = EditorialAdjustment(reporting_period=self.period, country=Country.objects.get(iso3="BGD"), reason="r")
        ma.save_model(req, obj, form=None, change=False)
        self.assertEqual(EditorialAdjustment.objects.get().created_by, user)
        self.assertFalse(admin.site._registry[SignalDaily].has_change_permission(req))
