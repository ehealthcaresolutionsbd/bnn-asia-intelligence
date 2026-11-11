from django.core.management.base import BaseCommand

from apps.sources.models import DataSource
from apps.sources.services import sync_source


class Command(BaseCommand):
    help = "Synchronise data sources now (all runnable, or --only slug1,slug2)."

    def add_arguments(self, p):
        p.add_argument("--only", default="")

    def handle(self, *a, only="", **o):
        qs = DataSource.objects.exclude(connector__in=["", "manual"])
        if only:
            qs = qs.filter(slug__in=only.split(","))
        for s in qs:
            log = sync_source(s, triggered_by="command")
            self.stdout.write(f"{s.slug:16} {log.status:8} fetched={log.items_fetched} new={log.items_created} "
                              f"skipped={log.items_skipped} {log.message[:120]}")
