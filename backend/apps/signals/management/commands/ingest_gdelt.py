import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import requests
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Sum

from apps.core.models import ReportingPeriod
from apps.signals import ingest
from apps.signals.models import IngestedDay


def _date(s):
    try:
        return date.fromisoformat(s)
    except ValueError as e:
        raise CommandError(f"Bad date {s!r} (use YYYY-MM-DD)") from e


class Command(BaseCommand):
    help = ("Ingest GDELT 1.0 daily event exports (one file per day ADDED) into SignalDaily/CountryVolumeDaily. "
            "Each file is counted at most once; see apps/signals/ingest.py for the idempotency design.")

    def add_arguments(self, p):
        p.add_argument("--start", required=True, help="First export file date, YYYY-MM-DD")
        p.add_argument("--end", help="Last export file date (default: yesterday UTC)")
        p.add_argument("--period", help="ReportingPeriod slug (default: the current period)")
        p.add_argument("--reset", action="store_true",
                       help="Delete ALL GDELT aggregates of the period and its file records, then re-ingest. "
                            "--start must then be on/before the period start.")
        p.add_argument("--retry-missing", action="store_true", help="Re-try days recorded as missing upstream.")
        p.add_argument("--workers", type=int, default=1, help="Parallel downloads (DB writes stay sequential).")

    def handle(self, *a, **o):
        start = _date(o["start"])
        end = _date(o["end"]) if o["end"] else date.today() - timedelta(days=1)
        if end < start:
            raise CommandError("--end is before --start")
        period = (ReportingPeriod.objects.filter(slug=o["period"]).first() if o["period"]
                  else ReportingPeriod.current())
        if period is None:
            raise CommandError("Reporting period not found.")

        if o["reset"]:
            if start > period.start_date:
                raise CommandError(f"--reset wipes the whole period {period}; --start must be <= {period.start_date} "
                                   f"or the days in between would be lost.")
            self.stdout.write(self.style.WARNING(f"Reset {period}: deleted {ingest.reset_period(period)}"))

        done = {d: s for d, s in IngestedDay.objects.filter(day__range=(start, end)).values_list("day", "status")}
        todo = [d for d in ingest.daterange(start, end)
                if done.get(d) not in ("ok",) and (done.get(d) != "missing" or o["retry_missing"])]
        skipped = (end - start).days + 1 - len(todo)
        self.stdout.write(f"Period {period} ({period.start_date}..{period.end_date}); files {start}..{end}: "
                          f"{len(todo)} to ingest, {skipped} already done/missing.")

        counts = {"ok": 0, "missing": 0, "failed": 0, "skipped": skipped}
        t0 = time.monotonic()
        workers = max(1, o["workers"])
        if workers == 1:
            results = (ingest.ingest_day(d, period=period, force=o["retry_missing"]) for d in todo)
            for i, r in enumerate(results, 1):
                self._report(i, len(todo), r, counts)
        else:
            session = requests.Session()
            adapter = requests.adapters.HTTPAdapter(pool_maxsize=workers)
            session.mount("https://", adapter)

            def fetch(d):
                try:
                    return d, ingest.fetch_export(d, session=session), None
                except Exception as e:  # noqa: BLE001
                    return d, None, e

            with ThreadPoolExecutor(max_workers=workers) as pool:
                for i, (d, path, err) in enumerate(pool.map(fetch, todo), 1):
                    url = ingest.export_url(d)
                    if err is not None:
                        rec = ingest.record_status(d, "failed", f"download: {type(err).__name__}: {err}", url)
                        r = ingest.IngestResult(d, "failed", rec, 0, str(err))
                    elif path is None:
                        rec = ingest.record_status(d, "missing", f"HTTP 404 for {url}", url)
                        r = ingest.IngestResult(d, "missing", rec, 0, "HTTP 404")
                    else:
                        r = ingest.ingest_day(d, period=period, force=o["retry_missing"], local_path=path)
                    self._report(i, len(todo), r, counts)

        rows = IngestedDay.objects.filter(day__range=(start, end), status="ok").aggregate(n=Sum("rows_asia"))["n"]
        self.stdout.write(self.style.SUCCESS(
            f"Done in {time.monotonic() - t0:.1f}s: {counts}. In-period Asian events counted from these files: "
            f"{rows or 0}"))

    def _report(self, i, n, r, counts):
        counts[r.status] = counts.get(r.status, 0) + 1
        style = {"ok": self.style.SUCCESS, "failed": self.style.ERROR, "missing": self.style.WARNING}.get(
            r.status, lambda x: x)
        extra = f"rows={r.record.rows_total} counted={r.record.rows_asia}" if r.status == "ok" else r.message
        self.stdout.write(style(f"[{i}/{n}] {r.day} {r.status:<7} {r.seconds:5.1f}s {extra}"))
