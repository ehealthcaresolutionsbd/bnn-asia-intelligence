"""Connectors for official APIs / datasets that produce IndicatorObservations."""
from __future__ import annotations

import csv
import datetime as dt
import io
import re

from apps.catalog.models import Indicator
from apps.core.models import Country
from apps.observations.models import IndicatorObservation

from .base import Connector, RunResult


def _upsert(indicator, country, period, source, value, ref_start, ref_end, label, url, published_at, *,
            counts, note="", data_status="final", rank=None, rank_of=None, dataset=None, auto_verify=True):
    """Create or update one observation. Official-provider data is auto-verified (it is the
    provider's own published figure); everything else enters as pending."""
    obj, created = IndicatorObservation.objects.update_or_create(
        indicator=indicator, country=country, reporting_period=period, reference_label=label, source=source,
        defaults=dict(value=value, reference_start=ref_start, reference_end=ref_end, source_url=url,
                      published_at=published_at, collected_at=Connector.now(), is_historical=not counts,
                      notes=note, data_status=data_status, published_rank=rank, published_rank_of=rank_of,
                      dataset=dataset,
                      verification_status="verified" if auto_verify else "pending",
                      verified_at=Connector.now() if auto_verify else None))
    return created


def _countries_by_iso3():
    return {c.iso3: c for c in Country.objects.all()}


class WorldBankConnector(Connector):
    """World Bank Indicators API v2 (open, no key). Used for WGI (source 3) and WDI (source 2)."""
    key = "worldbank"
    BASE = "https://api.worldbank.org/v2"

    def test(self):
        r = self.get(f"{self.BASE}/country/BGD/indicator/GOV_WGI_GE.EST", params={"source": 3, "format": "json", "per_page": 1, "mrv": 1})
        data = r.json()
        ok = isinstance(data, list) and len(data) > 1 and data[1]
        return bool(ok), f"WGI last updated {data[0].get('lastupdated')}" if ok else "Unexpected response"

    def run(self, period):
        res = RunResult()
        iso = _countries_by_iso3()
        codes = ";".join(iso.keys())
        for ind_code, wb_code, wb_source in self.cfg.get("indicators", []):
            indicator = Indicator.objects.filter(code=ind_code).first()
            if not indicator:
                res.messages.append(f"indicator {ind_code} missing")
                continue
            r = self.get(f"{self.BASE}/country/{codes}/indicator/{wb_code}",
                         params={"source": wb_source, "format": "json", "per_page": 2000, "mrv": 3})
            payload = r.json()
            if not isinstance(payload, list) or len(payload) < 2 or not payload[1]:
                res.messages.append(f"{wb_code}: no data")
                continue
            last_updated = payload[0].get("lastupdated")
            pub = dt.date.fromisoformat(last_updated) if last_updated else None
            for row in payload[1]:
                res.fetched += 1
                c = iso.get(row.get("countryiso3code"))
                if not c or row.get("value") is None:
                    res.skipped += 1   # missing stays missing – no zero rows
                    continue
                year = int(row["date"][:4])
                rs, re_ = self.year_bounds(year)
                # The dataset publication date only applies to the most recent year of the release.
                is_latest = year == max(int(x["date"][:4]) for x in payload[1] if x.get("countryiso3code") == c.iso3 and x.get("value") is not None)
                counts, note = self.counts_for(period, rs, re_, pub if is_latest else None)
                url = f"https://data.worldbank.org/indicator/{wb_code}?locations={c.iso2}" if wb_source == 2 else \
                      f"https://www.worldbank.org/en/publication/worldwide-governance-indicators"
                created = _upsert(indicator, c, period, self.source, float(row["value"]), rs, re_,
                                  f"{wb_code} {year}", url, pub if is_latest else None, counts=counts, note=note)
                res.created += created
                res.updated += (not created)
        return res


class TransparencyCPIConnector(Connector):
    """Transparency International CPI – public JSON used by transparency.org's own CPI pages."""
    key = "ti_cpi"
    URL = "https://www.transparency.org/en/api/latest/cpi"

    def test(self):
        d = self.get(self.URL).json()
        years = sorted({x["year"] for x in d})
        return bool(d), f"{len(d)} rows, years {years[0]}–{years[-1]}"

    def run(self, period):
        res = RunResult()
        indicator = Indicator.objects.get(code="ti_cpi_score")
        iso = _countries_by_iso3()
        data = self.get(self.URL).json()
        latest_year = max(x["year"] for x in data)
        totals = {}
        for x in data:
            totals[x["year"]] = totals.get(x["year"], 0) + 1
        # CPI for year N is published in late January / February of N+1.
        pub_date = dt.date(latest_year + 1, 2, 10)
        for x in data:
            if x["year"] < latest_year - 2:
                continue
            res.fetched += 1
            c = iso.get(x.get("iso3"))
            if not c or x.get("score") in (None, ""):
                res.skipped += 1
                continue
            rs, re_ = self.year_bounds(x["year"])
            counts, note = self.counts_for(period, rs, re_, pub_date if x["year"] == latest_year else None)
            created = _upsert(indicator, c, period, self.source, float(x["score"]), rs, re_, f"CPI {x['year']}",
                              f"https://www.transparency.org/en/cpi/{x['year']}/index/{c.iso3.lower()}",
                              pub_date if x["year"] == latest_year else None, counts=counts, note=note,
                              rank=x.get("rank"), rank_of=totals[x["year"]])
            res.created += created
            res.updated += (not created)
        return res


class IMFDataMapperConnector(Connector):
    """IMF DataMapper API (WEO). Current-year values are projections → stored as 'estimated'."""
    key = "imf"
    BASE = "https://www.imf.org/external/datamapper/api/v1"

    def test(self):
        d = self.get(f"{self.BASE}/NGDP_RPCH", params={"periods": str(dt.date.today().year)}).json()
        return "values" in d, "WEO datamapper reachable"

    def run(self, period):
        res = RunResult()
        iso = _countries_by_iso3()
        year = period.start_date.year
        for ind_code, imf_code in self.cfg.get("indicators", []):
            indicator = Indicator.objects.filter(code=ind_code).first()
            if not indicator:
                continue
            d = self.get(f"{self.BASE}/{imf_code}", params={"periods": f"{year - 1},{year}"}).json()
            series = d.get("values", {}).get(imf_code, {})
            for iso3, by_year in series.items():
                c = iso.get(iso3)
                if not c:
                    continue
                for y, v in by_year.items():
                    if int(y) not in (year - 1, year):
                        continue  # API may ignore `periods`; keep only the edition year and the year before
                    res.fetched += 1
                    if v is None:
                        res.skipped += 1
                        continue
                    y = int(y)
                    rs, re_ = self.year_bounds(y)
                    counts, note = self.counts_for(period, rs, re_)
                    status = "estimated" if y >= dt.date.today().year else "preliminary"
                    created = _upsert(indicator, c, period, self.source, float(v), rs, re_, f"WEO {imf_code} {y}",
                                      f"https://www.imf.org/external/datamapper/{imf_code}@WEO/{iso3}",
                                      None, counts=counts, note=note or "IMF World Economic Outlook estimate/projection.",
                                      data_status=status)
                    res.created += created
                    res.updated += (not created)
        return res


class UNDPHDRConnector(Connector):
    """UNDP Human Development Report composite indices (CSV time series)."""
    key = "undp_hdr"

    def test(self):
        r = self.get(self.cfg["csv_url"], stream=True)
        head = next(r.iter_lines()).decode("utf-8", "ignore")
        return "iso3" in head, "CSV header ok" if "iso3" in head else "Unexpected CSV"

    def run(self, period):
        res = RunResult()
        indicator = Indicator.objects.get(code="undp_hdi")
        iso = _countries_by_iso3()
        text = self.get(self.cfg["csv_url"]).content.decode("utf-8", "ignore")
        rows = list(csv.DictReader(io.StringIO(text)))
        hdi_cols = sorted([k for k in rows[0] if re.fullmatch(r"hdi_\d{4}", k)])
        last = hdi_cols[-1]
        year = int(last[-4:])
        pub = dt.date.fromisoformat(self.cfg.get("published", f"{year + 2}-05-06"))
        for row in rows:
            c = iso.get(row.get("iso3"))
            res.fetched += 1
            if not c or not row.get(last):
                res.skipped += 1
                continue
            rs, re_ = self.year_bounds(year)
            counts, note = self.counts_for(period, rs, re_, pub)
            created = _upsert(indicator, c, period, self.source, float(row[last]), rs, re_, f"HDI {year}",
                              "https://hdr.undp.org/data-center/human-development-index", pub, counts=counts, note=note)
            res.created += created
            res.updated += (not created)
        return res


class RSFIndexConnector(Connector):
    """RSF World Press Freedom Index – parses the public index page.

    Disabled by default: RSF's terms should be confirmed by BNN Asia before automated
    extraction. Until then researchers import the figures with the manual CSV importer.
    """
    key = "rsf_index"
    URL = "https://rsf.org/en/index"

    def test(self):
        h = self.get(self.URL).text
        n = len(re.findall(r'class="country-list-item js-country-name', h))
        return n > 100, f"{n} countries parsed from public index page"

    def run(self, period):
        res = RunResult()
        indicator = Indicator.objects.get(code="rsf_score")
        iso = _countries_by_iso3()
        h = self.get(self.URL).text
        year = int((re.search(r"/fiche-pays/\d+/(\d{4})", h) or [None, period.start_date.year])[1])
        items = re.findall(r'country-list-item js-country-name (\w{3})".*?country-list-item__position">(\d+)<.*?'
                           r'country-list-item__score[^>]*>\s*([\d.,]+)', h, flags=re.S)
        total = len(items)
        for iso3, pos, score in items:
            res.fetched += 1
            c = iso.get(iso3)
            if not c:
                res.skipped += 1
                continue
            rs, re_ = self.year_bounds(year)
            counts, note = self.counts_for(period, rs, re_)
            created = _upsert(indicator, c, period, self.source, float(score.replace(",", ".")), rs, re_, f"RSF {year}",
                              f"https://rsf.org/en/country/{c.name.lower().replace(' ', '-')}", dt.date(year, 5, 2),
                              counts=counts, note=note, rank=int(pos), rank_of=total)
            res.created += created
            res.updated += (not created)
        return res


class ManualDatasetConnector(Connector):
    """Placeholder for datasets that must be downloaded under a licence and imported by a researcher
    (Freedom House, World Justice Project, V-Dem). test() only checks the landing page is reachable."""
    key = "manual"

    def test(self):
        r = self.get(self.source.website)
        return False, f"Landing page HTTP {r.status_code}. Requires licensed download + CSV import (manage.py import_observations)."

    def run(self, period):
        res = RunResult()
        res.messages.append("Manual dataset – use import_observations with the downloaded file.")
        return res
