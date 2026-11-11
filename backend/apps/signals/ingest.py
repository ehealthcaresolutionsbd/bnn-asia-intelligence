"""GDELT 1.0 daily event export -> BNN signal aggregates.

Pipeline for one export file (the file for date D holds the events GDELT *added* on D):

1. ``fetch_export(D)`` streams ``https://data.gdeltproject.org/events/YYYYMMDD.export.CSV.zip`` to a
   temporary file (404 -> ``None``, i.e. "missing upstream").
2. ``aggregate_file()`` reads the zipped TSV row by row with the ``csv`` module (never loads the file into
   memory), keeps rows whose ActionGeo country (FIPS 10-4) maps to one of our ``Country`` rows and whose
   EVENT date (``sqldate``) falls inside the reporting period, and builds the per-file aggregates in memory.
   Edition rule: an event that happened in 2025 but was reported in a 2026 file is NOT counted for 2026.
3. ``apply_aggregates()`` adds the per-file aggregates to ``CountryVolumeDaily`` / ``SignalDaily`` and records
   ``IngestedDay`` in ONE transaction.

Idempotency design
------------------
Aggregates are keyed by EVENT day, but the events of one event day arrive spread over many export files
(today's file mentions yesterday's and last week's events). Aggregates therefore have to be *added to*, and
re-running a file would count it twice. The unit of idempotency is the ingested FILE:

* The increment of all aggregate rows and the creation of ``IngestedDay(day=<file date>, status="ok")`` happen
  in the same database transaction. Either the whole file is counted exactly once, or (on any error) nothing
  is, and the day is recorded as "failed" so a later run retries it. A Postgres advisory lock serialises the
  apply step across processes (management command, Celery worker), and the "already ingested?" check is
  repeated inside the lock, so two concurrent runs cannot both count the same file.
* A file that was ingested OK is never ingested again: ``ingest_day`` skips it, and ``force=True`` is REFUSED
  for it (``AlreadyIngested``). Subtracting a previous contribution is not possible reliably: the evidence
  URL lists cannot be "un-merged", and if the taxonomy in ``rules.py`` changed in between, recomputing the
  old contribution would give different numbers. ``force=True`` only re-tries days recorded as "missing"
  (those are skipped by default so a backfill does not hammer 404s again); "failed" days are always retried
  because they contributed nothing.
* To rebuild after a taxonomy change, use ``reset_period()`` (``ingest_gdelt --reset``): it deletes every
  aggregate whose event day lies in the period plus every ``IngestedDay`` from the period start onwards (no
  file before the period start can contain an in-period event), then everything is re-ingested from scratch.
"""
import csv
import io
import json
import logging
import tempfile
import time
import zipfile
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import requests
from django.conf import settings
from django.db import connection, transaction

from apps.core.models import Country, ReportingPeriod

from . import rules
from .models import CountryVolumeDaily, IngestedDay, SignalDaily

log = logging.getLogger(__name__)

URL_TEMPLATE = "https://data.gdeltproject.org/events/{:%Y%m%d}.export.CSV.zip"
MAX_SAMPLE_URLS = 5
_LOCK_KEY = 0x6764656C74  # "gdelt" – pg_advisory_xact_lock key for the apply step

C = rules.COL
_NCOLS = max(C.values()) + 1


class AlreadyIngested(Exception):
    """Raised when force re-ingesting a file that was already counted (would double count)."""


# --------------------------------------------------------------------------- classification

# Pre-compiled view of rules.SIGNALS: (key, prefixes, targets, perpetrators)
_RULES = [(key, tuple(spec[2]), spec[3], spec[4]) for key, spec in rules.SIGNALS.items()]


def classify(row):
    """Signal keys from ``rules.SIGNALS`` that a GDELT row matches.

    A row matches when its CAMEO EventCode starts with one of the rule's prefixes, AND (if the rule restricts
    targets) Actor2Type1Code is in the target set, AND (if it restricts perpetrators) Actor1Type1Code is in
    the perpetrator set. ``None`` means no constraint.
    """
    code = row[C["event_code"]].strip()
    if not code:
        return []
    a1, a2 = row[C["a1type"]].strip(), row[C["a2type"]].strip()
    out = []
    for key, prefixes, targets, perps in _RULES:
        if not code.startswith(prefixes):
            continue
        if targets is not None and a2 not in targets:
            continue
        if perps is not None and a1 not in perps:
            continue
        out.append(key)
    return out


def country_iso3(row):
    """ISO3 of the row's ActionGeo country (FIPS 10-4 -> ISO3; Gaza 'GZ' -> PSE), or None."""
    return rules.FIPS_TO_ISO3.get(row[C["geo_country"]].strip())


# --------------------------------------------------------------------------- aggregation (in memory)

def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _sqldate(v):
    try:
        return datetime.strptime(v.strip(), "%Y%m%d").date()
    except (AttributeError, ValueError):
        return None


@dataclass
class FileAggregate:
    rows_total: int = 0
    rows_asia_any_date: int = 0     # in one of our countries, any event date
    rows_out_of_period: int = 0     # in one of our countries but event date outside the period (e.g. 2025)
    rows_counted: int = 0
    rows_malformed: int = 0
    # (iso3, day) -> [events, articles]
    volume: dict = field(default_factory=lambda: defaultdict(lambda: [0, 0]))
    # (iso3, day, signal) -> dict
    signals: dict = field(default_factory=dict)

    def summary(self):
        return {"rows_total": self.rows_total, "rows_asia_any_date": self.rows_asia_any_date,
                "rows_out_of_period": self.rows_out_of_period, "rows_counted": self.rows_counted,
                "rows_malformed": self.rows_malformed, "volume_rows": len(self.volume),
                "signal_rows": len(self.signals)}


def aggregate_rows(rows, *, iso3s, period):
    """Aggregate an iterable of GDELT rows (lists of str). ``iso3s``: set of ISO3 codes we track."""
    agg = FileAggregate()
    start, end = period.start_date, period.end_date
    for row in rows:
        agg.rows_total += 1
        if len(row) < _NCOLS:
            agg.rows_malformed += 1
            continue
        iso3 = country_iso3(row)
        if iso3 is None or iso3 not in iso3s:
            continue
        agg.rows_asia_any_date += 1
        day = _sqldate(row[C["sqldate"]])
        if day is None or not (start <= day <= end):
            agg.rows_out_of_period += 1
            continue
        agg.rows_counted += 1
        articles = _int(row[C["articles"]])
        vol = agg.volume[(iso3, day)]
        vol[0] += 1
        vol[1] += articles
        keys = classify(row)
        if not keys:
            continue
        mentions, sources = _int(row[C["mentions"]]), _int(row[C["sources"]])
        goldstein, tone = _float(row[C["goldstein"]]), _float(row[C["tone"]])
        url = row[C["url"]].strip()
        for key in keys:
            s = agg.signals.get((iso3, day, key))
            if s is None:
                s = agg.signals[(iso3, day, key)] = {"events": 0, "mentions": 0, "sources": 0, "articles": 0,
                                                     "goldstein_sum": 0.0, "tone_sum": 0.0, "sample_urls": []}
            s["events"] += 1
            s["mentions"] += mentions
            s["sources"] += sources
            s["articles"] += articles
            s["goldstein_sum"] += goldstein
            s["tone_sum"] += tone
            if url and len(s["sample_urls"]) < MAX_SAMPLE_URLS and url not in s["sample_urls"]:
                s["sample_urls"].append(url)
    return agg


def iter_export_rows(path):
    """Stream rows from a GDELT export: a .zip (first member) or a plain tab-separated file."""
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as zf:
            with zf.open(zf.namelist()[0]) as raw:
                text = io.TextIOWrapper(raw, encoding="utf-8", errors="replace", newline="")
                yield from csv.reader(text, delimiter="\t", quoting=csv.QUOTE_NONE)
    else:
        with open(path, encoding="utf-8", errors="replace", newline="") as fh:
            yield from csv.reader(fh, delimiter="\t", quoting=csv.QUOTE_NONE)


def aggregate_file(path, *, period, iso3s=None):
    if iso3s is None:
        iso3s = set(Country.objects.values_list("iso3", flat=True))
    return aggregate_rows(iter_export_rows(path), iso3s=iso3s, period=period)


# --------------------------------------------------------------------------- download

def export_url(day):
    return URL_TEMPLATE.format(day)


def fetch_export(day, *, session=None):
    """Download the export zip for ``day`` to a temp file and return its path, or None if upstream has no file.

    The caller owns (and must delete) the returned file.
    """
    http = session or requests
    url = export_url(day)
    timeout = (10, getattr(settings, "HTTP_TIMEOUT", 30) * 4)
    with http.get(url, stream=True, timeout=timeout,
                  headers={"User-Agent": settings.HTTP_USER_AGENT}) as resp:
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        tmp = tempfile.NamedTemporaryFile(prefix=f"gdelt-{day:%Y%m%d}-", suffix=".zip", delete=False)
        try:
            with tmp:
                for chunk in resp.iter_content(chunk_size=1 << 16):
                    if chunk:
                        tmp.write(chunk)
        except BaseException:
            _unlink(tmp.name)
            raise
    return tmp.name


def _unlink(path):
    import os
    try:
        os.unlink(path)
    except OSError:
        pass


# --------------------------------------------------------------------------- apply (database)

def _lock():
    if connection.vendor == "postgresql":
        with connection.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(%s)", [_LOCK_KEY])


def apply_aggregates(day, agg, *, source_url):
    """Add one file's aggregates to the daily tables and mark the file ingested – atomically.

    Returns the IngestedDay, or raises AlreadyIngested if another run counted the file meanwhile.
    """
    countries = dict(Country.objects.values_list("iso3", "id"))
    with transaction.atomic():
        _lock()
        if IngestedDay.objects.filter(day=day, status="ok").exists():
            raise AlreadyIngested(f"{day} was ingested concurrently")

        # --- country volume
        if agg.volume:
            days = {d for _, d in agg.volume}
            existing = {(o.country_id, o.day): o for o in CountryVolumeDaily.objects.select_for_update()
                        .filter(day__in=days, country_id__in={countries[i] for i, _ in agg.volume})}
            new, upd = [], []
            for (iso3, d), (events, articles) in agg.volume.items():
                o = existing.get((countries[iso3], d))
                if o is None:
                    new.append(CountryVolumeDaily(country_id=countries[iso3], day=d, events=events, articles=articles))
                else:
                    o.events += events
                    o.articles += articles
                    upd.append(o)
            CountryVolumeDaily.objects.bulk_create(new, batch_size=1000)
            CountryVolumeDaily.objects.bulk_update(upd, ["events", "articles"], batch_size=1000)

        # --- signals
        if agg.signals:
            days = {d for _, d, _ in agg.signals}
            existing = {(o.country_id, o.day, o.signal): o for o in SignalDaily.objects.select_for_update()
                        .filter(day__in=days, country_id__in={countries[i] for i, _, _ in agg.signals},
                                signal__in={k for _, _, k in agg.signals})}
            new, upd = [], []
            num = ("events", "mentions", "sources", "articles", "goldstein_sum", "tone_sum")
            for (iso3, d, key), s in agg.signals.items():
                o = existing.get((countries[iso3], d, key))
                if o is None:
                    new.append(SignalDaily(country_id=countries[iso3], day=d, signal=key, **s))
                    continue
                for f in num:
                    setattr(o, f, getattr(o, f) + s[f])
                urls = list(o.sample_urls or [])
                for u in s["sample_urls"]:
                    if len(urls) >= MAX_SAMPLE_URLS:
                        break
                    if u not in urls:
                        urls.append(u)
                o.sample_urls = urls
                upd.append(o)
            SignalDaily.objects.bulk_create(new, batch_size=1000)
            SignalDaily.objects.bulk_update(upd, [*num, "sample_urls"], batch_size=1000)

        rec, _ = IngestedDay.objects.update_or_create(day=day, defaults={
            "source_url": source_url, "rows_total": agg.rows_total, "rows_asia": agg.rows_counted,
            "status": "ok", "message": json.dumps(agg.summary())})
    return rec


def record_status(day, status, message, source_url):
    """Record a non-ok outcome ("missing"/"failed"). Never downgrades a file that is already counted ("ok")."""
    fields = {"source_url": source_url, "rows_total": 0, "rows_asia": 0, "status": status, "message": message[:5000]}
    with transaction.atomic():
        _lock()
        rec = IngestedDay.objects.filter(day=day).first()
        if rec is None:
            return IngestedDay.objects.create(day=day, **fields)
        if rec.status != "ok":
            for k, v in fields.items():
                setattr(rec, k, v)
            rec.save()
        return rec


# --------------------------------------------------------------------------- public entry points

@dataclass
class IngestResult:
    day: date
    status: str              # ok | skipped | missing | failed
    record: IngestedDay = None
    seconds: float = 0.0
    message: str = ""


def ingest_day(day, *, period=None, force=False, local_path=None, session=None):
    """Ingest the GDELT export FILE of ``day`` (events added on that day) – see module docstring.

    * already "ok"      -> skipped; with ``force=True`` raises ``AlreadyIngested`` (would double count).
    * already "missing" -> skipped unless ``force=True``.
    * "failed"/new      -> processed.
    * HTTP 404          -> IngestedDay(status="missing"), no exception.
    * any other error   -> IngestedDay(status="failed", message=error), no exception (backfills continue).

    ``local_path``: an already downloaded export (zip or tsv) – used by the command's download pool.
    The temp file is deleted afterwards either way.
    """
    t0 = time.monotonic()
    period = period or ReportingPeriod.current()
    if period is None:
        raise RuntimeError("No current ReportingPeriod – pass period= or mark one as current.")
    url = export_url(day)
    prev = IngestedDay.objects.filter(day=day).first()
    if prev and prev.status == "ok":
        if force:
            _cleanup(local_path)
            raise AlreadyIngested(
                f"{day} is already counted; re-ingesting would double count. Use `ingest_gdelt --reset` to rebuild "
                f"the period from scratch.")
        _cleanup(local_path)
        return IngestResult(day, "skipped", prev, time.monotonic() - t0, "already ingested")
    if prev and prev.status == "missing" and not force:
        _cleanup(local_path)
        return IngestResult(day, "skipped", prev, time.monotonic() - t0, "missing upstream (use force to retry)")

    path = local_path
    try:
        if path is None:
            path = fetch_export(day, session=session)
        if path is None:
            rec = record_status(day, "missing", f"HTTP 404 for {url}", url)
            return IngestResult(day, "missing", rec, time.monotonic() - t0, "HTTP 404")
        agg = aggregate_file(path, period=period)
        rec = apply_aggregates(day, agg, source_url=url)
        return IngestResult(day, "ok", rec, time.monotonic() - t0, json.dumps(agg.summary()))
    except AlreadyIngested as e:
        return IngestResult(day, "skipped", IngestedDay.objects.filter(day=day).first(), time.monotonic() - t0, str(e))
    except Exception as e:  # noqa: BLE001 – record and continue
        log.exception("GDELT ingest failed for %s", day)
        rec = record_status(day, "failed", f"{type(e).__name__}: {e}", url)
        return IngestResult(day, "failed", rec, time.monotonic() - t0, f"{type(e).__name__}: {e}")
    finally:
        _cleanup(path)


def _cleanup(path):
    if path:
        _unlink(path)


def reset_period(period):
    """Wipe all GDELT aggregates of ``period`` and the file records that may have contributed to them.

    Files dated before the period start cannot hold in-period events (event date <= date added), so every
    IngestedDay from ``period.start_date`` on is removed. Returns a dict of deleted counts.
    """
    with transaction.atomic():
        _lock()
        rng = (period.start_date, period.end_date)
        n_sig, _ = SignalDaily.objects.filter(day__range=rng).delete()
        n_vol, _ = CountryVolumeDaily.objects.filter(day__range=rng).delete()
        n_days, _ = IngestedDay.objects.filter(day__gte=period.start_date).delete()
    return {"signal_daily": n_sig, "country_volume_daily": n_vol, "ingested_day": n_days}


def daterange(start, end):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)
