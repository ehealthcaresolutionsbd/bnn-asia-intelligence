import time

from django.core.management.base import BaseCommand, CommandError

from apps.core.models import Country, ReportingPeriod
from apps.reports.builder import build_all


class Command(BaseCommand):
    help = ("Generate data-driven annual country reports for all active countries (current period). Each run creates a "
            "new version per country; countries whose latest report is locked by an editor are skipped.")

    def add_arguments(self, parser):
        parser.add_argument("--country", help="ISO3 code of a single country, e.g. BGD.")
        parser.add_argument("--period", help="Reporting period slug (default: current period).")
        parser.add_argument("--no-publish", action="store_true", help="Create drafts instead of published reports.")

    def handle(self, *args, **opts):
        period = (ReportingPeriod.objects.filter(slug=opts["period"]).first() if opts["period"]
                  else ReportingPeriod.current())
        if not period:
            raise CommandError("No reporting period found (set a current period or pass --period).")
        if opts["country"] and not Country.objects.filter(iso3=opts["country"].upper(), is_active=True).exists():
            raise CommandError(f"No active country with ISO3 {opts['country'].upper()}.")
        t0 = time.monotonic()

        def line(country, r):
            if r.skipped_locked:
                self.stdout.write(f"  {country.iso3}  skipped – v{r.version} is locked")
            else:
                n = len((r.sections.get("findings") or {}).get("items", []))
                self.stdout.write(f"  {country.iso3}  v{r.version} {r.status:<9} {len(r.charts)} charts, {n} findings")

        self.stdout.write(f"Generating {period.name} reports…")
        results = build_all(period, iso3=opts["country"], publish=not opts["no_publish"], stdout=line)
        built = sum(1 for *_, skipped in results if not skipped)
        skipped = len(results) - built
        self.stdout.write(self.style.SUCCESS(
            f"Done: {built} report(s) generated, {skipped} skipped (locked) in {time.monotonic() - t0:.1f}s."))
