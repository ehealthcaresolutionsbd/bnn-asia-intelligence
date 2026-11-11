"""RSS collection + Stage B (assistive) processing.

Stores only feed metadata and the feed's own short summary (≤600 chars) with a link back –
never full article text. Country/type detection only creates *suggestions* and triage tasks;
it never creates or publishes an incident.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import html
import re

import feedparser
from django.utils import timezone

from apps.core.models import Country
from apps.core.seed_data import INCIDENT_KEYWORDS

from .base import Connector, RunResult

TAG_RE = re.compile(r"<[^>]+>")
NUM_RE = re.compile(r"\b(\d{1,5})\s+(?:people|persons|journalists|protesters|activists|students|killed|dead|injured|arrested|detained)\b", re.I)
DATE_RE = re.compile(r"\b(\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+20\d\d)\b")


def clean(text, limit=600):
    t = html.unescape(TAG_RE.sub(" ", text or ""))
    t = re.sub(r"\s+", " ", t).strip()
    return t[:limit]


def country_patterns():
    pats = []
    for c in Country.objects.filter(is_active=True):
        names = [c.name] + list(c.aliases or [])
        pats.append((c, re.compile(r"\b(" + "|".join(re.escape(n) for n in names) + r")\b", re.I)))
    return pats


def detect(text, pats):
    countries = [c for c, p in pats if p.search(text)]
    low = text.lower()
    types = [slug for slug, kws in INCIDENT_KEYWORDS.items() if any(k in low for k in kws)]
    numbers = [int(n) for n in NUM_RE.findall(text)]
    dates = DATE_RE.findall(text)
    return countries, types, {"numbers": numbers, "dates": dates}


class RSSConnector(Connector):
    key = "rss"

    def test(self):
        f = feedparser.parse(self.get(self.source.endpoint).content)
        n = len(f.entries)
        return n > 0, f"{n} entries; feed title: {f.feed.get('title', '?')[:60]}"

    def run(self, period):
        from apps.incidents.models import IncidentType, NewsArticle, VerificationTask
        res = RunResult()
        feed = feedparser.parse(self.get(self.source.endpoint).content)
        pats = country_patterns()
        types = {t.slug: t for t in IncidentType.objects.all()}
        for e in feed.entries:
            res.fetched += 1
            url = e.get("link")
            if not url or NewsArticle.objects.filter(url=url).exists():
                res.skipped += 1
                continue
            title = clean(e.get("title"), 500)
            summary = clean(e.get("summary") or e.get("description"))
            pub = None
            for k in ("published_parsed", "updated_parsed"):
                if e.get(k):
                    pub = dt.datetime(*e[k][:6], tzinfo=dt.timezone.utc)
                    break
            countries, tslugs, extracted = detect(f"{title}. {summary}", pats)
            art = NewsArticle.objects.create(
                source=self.source, url=url, title=title, excerpt=summary, published_at=pub,
                collected_at=timezone.now(), ai_extracted=extracted,
                content_hash=hashlib.sha256((title + summary).encode()).hexdigest(),
                triage_status="new" if countries else "irrelevant")
            if countries:
                art.detected_countries.set(countries)
                art.detected_types.set([types[s] for s in tslugs if s in types])
                in_period = pub is None or period.start_date <= pub.date() <= period.end_date
                VerificationTask.objects.create(kind="triage_article", article=art, priority=2 if tslugs else 4,
                                                notes="" if in_period else "Published outside the reporting period.")
            res.created += 1
        return res
