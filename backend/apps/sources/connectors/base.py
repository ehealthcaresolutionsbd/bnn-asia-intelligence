from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass, field

import requests
from django.conf import settings
from django.utils import timezone

log = logging.getLogger(__name__)


@dataclass
class RunResult:
    fetched: int = 0
    created: int = 0
    updated: int = 0
    skipped: int = 0
    messages: list[str] = field(default_factory=list)

    @property
    def status(self):
        if self.fetched == 0 and self.messages:
            return "failed"
        return "partial" if self.messages else "success"


class Connector:
    """Base class. Subclasses implement test() and run()."""
    key = ""
    requires_key_env = ""

    def __init__(self, source):
        self.source = source
        self.http = requests.Session()
        self.http.headers["User-Agent"] = settings.HTTP_USER_AGENT
        self.cfg = source.config or {}

    def get(self, url, **kw):
        kw.setdefault("timeout", settings.HTTP_TIMEOUT)
        r = self.http.get(url, **kw)
        r.raise_for_status()
        return r

    def test(self) -> tuple[bool, str]:
        raise NotImplementedError

    def run(self, period) -> RunResult:
        raise NotImplementedError

    # ---- helpers -----------------------------------------------------------
    @staticmethod
    def year_bounds(year: int):
        return dt.date(year, 1, 1), dt.date(year, 12, 31)

    @staticmethod
    def now():
        return timezone.now()

    def counts_for(self, period, ref_start, ref_end, published_at=None):
        """Edition rule: a value counts for the period if its reference period overlaps it, or the
        source edition was published inside the period (e.g. CPI 2025 released Feb 2026 is the
        2026-edition value). Anything else is stored as historical reference only."""
        overlaps = ref_start <= period.end_date and ref_end >= period.start_date
        published_inside = published_at is not None and period.start_date <= published_at <= period.end_date
        note = ""
        if not overlaps and published_inside:
            note = (f"Latest edition published {published_at:%d %b %Y} (inside the {period.name} reporting period); "
                    f"describes {ref_start.year}.")
        return (overlaps or published_inside), note
