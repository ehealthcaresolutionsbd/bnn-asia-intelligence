from django.core.management.base import BaseCommand

from apps.core.models import ReportingPeriod
from apps.rankings.engine import calculate, publish
from apps.rankings.models import RankingMethodology


class Command(BaseCommand):
    help = "Calculate a draft BNN Asia Index snapshot (optionally --publish)."

    def add_arguments(self, p):
        p.add_argument("--publish", action="store_true")
        p.add_argument("--methodology", type=int)

    def handle(self, *a, publish_=False, methodology=None, **o):
        m = RankingMethodology.objects.get(pk=methodology) if methodology else \
            RankingMethodology.objects.filter(reporting_period=ReportingPeriod.current()).order_by("-created_at").first()
        snap = calculate(m, note="command")
        ranked = snap.scores.filter(category=None, is_ranked=True).count()
        self.stdout.write(f"Snapshot {snap.pk}: overall_available={snap.overall_available} ranked={ranked} "
                          f"weights={snap.effective_weights} {snap.unavailable_reason}")
        if o.get("publish"):
            publish(snap)
            self.stdout.write("published")
