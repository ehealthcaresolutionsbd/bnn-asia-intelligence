"""Import a researcher-prepared CSV of observations (for licensed datasets such as Freedom House, WJP, V-Dem,
or RSF while automation is disabled). Imported rows are 'pending' until a researcher verifies them.

CSV columns: iso3,indicator_code,value,reference_year,source_slug,source_url,published_at(YYYY-MM-DD),rank,rank_of,data_status
"""
import csv
import datetime as dt

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.catalog.models import Indicator
from apps.core.models import Country, ReportingPeriod
from apps.observations.models import IndicatorObservation
from apps.sources.connectors.base import Connector
from apps.sources.models import DataSource


class Command(BaseCommand):
    def add_arguments(self, p):
        p.add_argument("csv_path")

    def handle(self, csv_path, **o):
        period = ReportingPeriod.current()
        n = 0
        with open(csv_path, newline="", encoding="utf-8-sig") as f:
            for i, row in enumerate(csv.DictReader(f), start=2):
                try:
                    c = Country.objects.get(iso3=row["iso3"].strip().upper())
                    ind = Indicator.objects.get(code=row["indicator_code"].strip())
                    src = DataSource.objects.get(slug=row["source_slug"].strip())
                except Exception as e:
                    raise CommandError(f"line {i}: {e}")
                if row.get("value", "").strip() == "":
                    continue  # missing stays missing
                y = int(row["reference_year"])
                pub = dt.date.fromisoformat(row["published_at"]) if row.get("published_at") else None
                counts, note = Connector.counts_for(None, period, dt.date(y, 1, 1), dt.date(y, 12, 31), pub)
                IndicatorObservation.objects.update_or_create(
                    indicator=ind, country=c, reporting_period=period, reference_label=f"{src.slug} {y}", source=src,
                    defaults=dict(value=float(row["value"]), reference_start=dt.date(y, 1, 1), reference_end=dt.date(y, 12, 31),
                                  source_url=row["source_url"], published_at=pub, collected_at=timezone.now(),
                                  is_historical=not counts, notes=note, data_status=row.get("data_status") or "final",
                                  published_rank=int(row["rank"]) if row.get("rank") else None,
                                  published_rank_of=int(row["rank_of"]) if row.get("rank_of") else None,
                                  verification_status="pending"))
                n += 1
        self.stdout.write(f"Imported {n} observations as pending verification.")
