"""Idempotent bootstrap: regions, countries, 2026 reporting period, categories, indicators,
incident types, data-source registry, methodologies v1.0.0 and v2.0.0 (draft) and user groups.
Creates NO scores, rankings or observations."""
import datetime as dt

from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from apps.catalog.models import Indicator, IntelligenceCategory
from apps.core.models import Country, Region, ReportingPeriod
from apps.core.seed_data import CATEGORIES, COUNTRIES, INCIDENT_TYPES, REGIONS
from apps.incidents.models import IncidentType
from apps.rankings.models import MethodologyWeight, RankingMethodology
from apps.sources.models import DataSource

WGI = "https://www.worldbank.org/en/publication/worldwide-governance-indicators"

SOURCES = [
    # name, slug, org, website, kind, method, endpoint, connector, config, reliability, status, active, notes
    ("World Bank – Worldwide Governance Indicators", "wb-wgi", "World Bank", WGI, "original", "api",
     "https://api.worldbank.org/v2", "worldbank",
     {"indicators": [["wgi_ge", "GOV_WGI_GE.EST", 3], ["wgi_rq", "GOV_WGI_RQ.EST", 3], ["wgi_cc", "GOV_WGI_CC.EST", 3],
                     ["wgi_rl", "GOV_WGI_RL.EST", 3], ["wgi_va", "GOV_WGI_VA.EST", 3], ["wgi_pv", "GOV_WGI_PV.EST", 3],
                     ["wgi_va_hr", "GOV_WGI_VA.EST", 3], ["wgi_va_pf", "GOV_WGI_VA.EST", 3]]},
     5, "configured", True, "CC BY 4.0. Attribution: World Bank, Worldwide Governance Indicators."),
    ("World Bank – World Development Indicators", "wb-wdi", "World Bank", "https://data.worldbank.org", "original", "api",
     "https://api.worldbank.org/v2", "worldbank",
     {"indicators": [["population", "SP.POP.TOTL", 2], ["wdi_gdp_pc", "NY.GDP.PCAP.CD", 2],
                     ["wdi_poverty", "SI.POV.DDAY", 2]]},
     5, "configured", True, "CC BY 4.0."),
    ("Transparency International – Corruption Perceptions Index", "ti-cpi", "Transparency International",
     "https://www.transparency.org/en/cpi", "original", "dataset", "https://www.transparency.org/en/api/latest/cpi", "ti_cpi",
     {}, 5, "restricted", False, "CPI data is CC BY-ND 4.0: cite TI, do not alter scores. transparency.org bot protection "
     "returns HTTP 403 to automated clients (tested 2026-11-12), so automation is off and not circumvented: download the CPI "
     "results file from transparency.org and use import_observations. Automated fallback for corruption: WGI Control of Corruption."),
    ("IMF – World Economic Outlook (DataMapper)", "imf-weo", "International Monetary Fund",
     "https://www.imf.org/external/datamapper", "original", "api", "https://www.imf.org/external/datamapper/api/v1", "imf",
     {"indicators": [["imf_gdp_growth", "NGDP_RPCH"], ["imf_inflation", "PCPIPCH"], ["imf_unemployment", "LUR"]]},
     5, "configured", True, "IMF data – free reuse with attribution (IMF copyright & usage terms)."),
    ("UNDP – Human Development Report", "undp-hdr", "UNDP", "https://hdr.undp.org", "original", "dataset",
     "https://hdr.undp.org/sites/default/files/2025_HDR/HDR25_Composite_indices_complete_time_series.csv", "undp_hdr",
     {"csv_url": "https://hdr.undp.org/sites/default/files/2025_HDR/HDR25_Composite_indices_complete_time_series.csv",
      "published": "2025-05-06"}, 5, "configured", True, "CC BY 3.0 IGO."),
    ("RSF – World Press Freedom Index", "rsf-index", "Reporters Without Borders", "https://rsf.org/en/index", "original",
     "scrape_permitted", "https://rsf.org/en/index", "rsf_index", {}, 5, "restricted", False,
     "Automated extraction disabled until BNN Asia confirms RSF reuse terms; import figures manually meanwhile."),
    ("Freedom House – Freedom in the World", "fh-fiw", "Freedom House", "https://freedomhouse.org/report/freedom-world",
     "original", "dataset", "", "manual", {}, 5, "configured", True,
     "Download 'All data' Excel from freedomhouse.org (registration) and import. Attribution required."),
    ("World Justice Project – Rule of Law Index", "wjp-rli", "World Justice Project",
     "https://worldjusticeproject.org/rule-of-law-index/", "original", "dataset", "", "manual", {}, 5, "configured", True,
     "Download the WJP Rule of Law Index dataset and import. Non-commercial use with attribution."),
    ("V-Dem Institute – V-Dem Dataset", "vdem", "V-Dem Institute", "https://v-dem.net/data/the-v-dem-dataset/",
     "original", "dataset", "", "manual", {}, 5, "configured", True, "CC BY-SA 4.0. Large CSV – import selected indices."),
    ("CPJ – news feed", "cpj-rss", "Committee to Protect Journalists", "https://cpj.org", "secondary", "rss",
     "https://cpj.org/feed/", "rss", {}, 5, "configured", True, "Metadata + feed summary only, link back."),
    ("RSF – news feed", "rsf-rss", "Reporters Without Borders", "https://rsf.org", "secondary", "rss",
     "https://rsf.org/en/rss", "rss", {}, 5, "configured", True, "Metadata + feed summary only, link back."),
    ("Amnesty International – news feed", "amnesty-rss", "Amnesty International", "https://www.amnesty.org", "secondary",
     "rss", "https://www.amnesty.org/en/feed/", "rss", {}, 5, "configured", True, "Metadata + feed summary only."),
    ("Human Rights Watch – news feed", "hrw-rss", "Human Rights Watch", "https://www.hrw.org", "secondary", "rss",
     "https://www.hrw.org/rss/news", "rss", {}, 5, "configured", True, "Metadata + feed summary only."),
    ("OHCHR – news feed", "ohchr-rss", "UN OHCHR", "https://www.ohchr.org", "original", "rss",
     "https://www.ohchr.org/en/rss.xml", "rss", {}, 5, "configured", True, "UN content – attribution."),
    ("Transparency International Bangladesh", "tib", "TIB", "https://www.ti-bangladesh.org/en", "original", "manual", "",
     "manual", {}, 4, "configured", True, "No public RSS found (feed URL 404). Researchers add TIB reports manually."),
    ("BNN Asia – verified incident database", "bnn-incidents", "BNN Asia", "https://bnnasia.org", "original", "manual",
     "", "", {}, 4, "configured", True, "Internal: indicators aggregated from verified incidents."),
    ("BNN Asia – event data analysis (GDELT)", "bnn-signals", "BNN Asia", "https://bnnasia.org", "original", "dataset",
     "", "", {}, 4, "configured", True,
     "Internal: BNN Asia's own statistics computed from the GDELT event data (daily export)base (open data, free reuse with "
     "attribution to the GDELT Project). Machine-coded media events, coverage-corrected, with bootstrap intervals."),
]

INDICATORS = [
    # code, category, name, unit, type, direction, min, max, per_capita, scored, source slug, weight
    ("wgi_ge", "good-governance", "Government Effectiveness (WGI)", "est.", "score", "higher_better", -2.5, 2.5, False, True, "wb-wgi", 1),
    ("wgi_rq", "good-governance", "Regulatory Quality (WGI)", "est.", "score", "higher_better", -2.5, 2.5, False, True, "wb-wgi", 1),
    ("wgi_cc", "good-governance", "Control of Corruption (WGI)", "est.", "score", "higher_better", -2.5, 2.5, False, True, "wb-wgi", 1),
    ("ti_cpi_score", "good-governance", "Corruption Perceptions Index", "0–100", "score", "higher_better", 0, 100, False, True, "ti-cpi", 1.5),
    ("wgi_rl", "rule-of-law", "Rule of Law (WGI)", "est.", "score", "higher_better", -2.5, 2.5, False, True, "wb-wgi", 1),
    ("wjp_rli", "rule-of-law", "WJP Rule of Law Index", "0–1", "score", "higher_better", 0, 1, False, True, "wjp-rli", 1.5),
    ("wgi_va", "freedom-democracy", "Voice and Accountability (WGI)", "est.", "score", "higher_better", -2.5, 2.5, False, True, "wb-wgi", 3),
    ("wgi_pv", "freedom-democracy", "Political Stability & Absence of Violence (WGI)", "est.", "score", "higher_better", -2.5, 2.5, False, False, "wb-wgi", 0.5),
    ("fh_total", "freedom-democracy", "Freedom in the World total score", "0–100", "score", "higher_better", 0, 100, False, True, "fh-fiw", 1.5),
    ("rsf_score", "press-freedom", "RSF Press Freedom score", "0–100", "score", "higher_better", 0, 100, False, True, "rsf-index", 2),
    ("bnn_journalists_killed", "press-freedom", "Journalists killed (verified, BNN)", "count", "count", "lower_better", None, None, False, True, "bnn-incidents", 1),
    ("bnn_journalists_detained", "press-freedom", "Journalists arrested/disappeared (verified, BNN)", "count", "count", "lower_better", None, None, False, True, "bnn-incidents", 1),
    ("bnn_fox_violations", "press-freedom", "Freedom of expression violations (verified, BNN)", "count", "count", "lower_better", None, None, False, True, "bnn-incidents", 0.5),
    ("bnn_disappearances", "human-rights", "Enforced disappearances per million (verified, BNN)", "per million", "rate", "lower_better", None, None, True, True, "bnn-incidents", 1),
    ("bnn_killings_custody", "human-rights", "Extrajudicial killing allegations & custodial deaths per million", "per million", "rate", "lower_better", None, None, True, True, "bnn-incidents", 1),
    ("bnn_arbitrary_detention", "human-rights", "Arbitrary arrests & political detentions per million", "per million", "rate", "lower_better", None, None, True, True, "bnn-incidents", 1),
    ("bnn_torture", "human-rights", "Torture reports per million (verified, BNN)", "per million", "rate", "lower_better", None, None, True, True, "bnn-incidents", 0.5),
    ("imf_gdp_growth", "economic-social", "Real GDP growth", "%", "rate", "higher_better", -10, 10, False, True, "imf-weo", 1),
    ("imf_inflation", "economic-social", "Inflation (CPI, annual)", "%", "rate", "lower_better", 0, 30, False, True, "imf-weo", 1),
    ("imf_unemployment", "economic-social", "Unemployment rate", "%", "rate", "lower_better", 0, 25, False, True, "imf-weo", 1),
    ("wdi_gdp_pc", "economic-social", "GDP per capita (current US$)", "US$", "currency", "higher_better", None, None, False, False, "wb-wdi", 1),
    ("wdi_poverty", "economic-social", "Poverty headcount at $3.00/day", "%", "rate", "lower_better", 0, 100, False, False, "wb-wdi", 1),
    ("undp_hdi", "economic-social", "Human Development Index", "0–1", "score", "higher_better", 0, 1, False, True, "undp-hdr", 1),
    ("population", "economic-social", "Population (denominator only)", "people", "count", "higher_better", None, None, False, False, "wb-wdi", 0),
    # BNN Asia's own event-data statistics (apps.signals.indicators). Weights let them carry a category on their own
    # (≥50 % of its indicator weight) where international indices or verified incidents are missing.
    ("bnn_sig_media_repression", "press-freedom", "Coercion/violence against media per 1,000 events (BNN event data)", "per 1,000 events", "rate", "lower_better", None, None, False, True, "bnn-signals", 3),
    ("bnn_sig_censorship", "press-freedom", "Bans, restrictions & censorship per 1,000 events (BNN event data)", "per 1,000 events", "rate", "lower_better", None, None, False, True, "bnn-signals", 2),
    ("bnn_sig_state_repression", "human-rights", "State repression of civilians & civil society per 1,000 events (BNN event data)", "per 1,000 events", "rate", "lower_better", None, None, False, True, "bnn-signals", 1.5),
    ("bnn_sig_arrests", "human-rights", "Arrests & detentions by state actors per 1,000 events (BNN event data)", "per 1,000 events", "rate", "lower_better", None, None, False, True, "bnn-signals", 1),
    ("bnn_sig_violence", "human-rights", "Killings & physical assaults per 1,000 events (BNN event data)", "per 1,000 events", "rate", "lower_better", None, None, False, True, "bnn-signals", 1.5),
    # Independent anchor (v2.2.0): event data under-reports abuses where media are closed, so WGI Voice & Accountability
    # (civil liberties, freedom of expression and media) is blended into the two event-driven categories.
    ("wgi_va_hr", "human-rights", "Civil liberties anchor – Voice & Accountability (WGI)", "est.", "score", "higher_better", -2.5, 2.5, False, True, "wb-wgi", 4),
    ("wgi_va_pf", "press-freedom", "Media & expression anchor – Voice & Accountability (WGI)", "est.", "score", "higher_better", -2.5, 2.5, False, True, "wb-wgi", 5),
    ("bnn_sig_protest_repression", "freedom-democracy", "Share of protest events met with repression (BNN event data)", "%", "rate", "lower_better", None, None, False, True, "bnn-signals", 1),
]

# Indicators normalised on log(1 + x): event rates are heavily right-skewed (a few conflict countries dominate).
LOG_TRANSFORM = {"bnn_sig_media_repression", "bnn_sig_censorship", "bnn_sig_state_repression", "bnn_sig_arrests",
                 "bnn_sig_violence"}

V2_DESCRIPTION = (
    "BNN Asia's own annual index, computed from big data BNN Asia collects itself. (1) Event data: every daily GDELT "
    "event export is processed; events located in one of 48 Asian countries are classified into public BNN signals "
    "(CAMEO event code + actor-type rules, listed on this page). (2) Coverage correction: signal counts are divided by "
    "ALL events recorded in that country in the same period (rate per 1,000 events; protest repression as % of protest "
    "events), so countries with more media coverage are not penalised for being reported on more. Countries with fewer "
    "than 300 in-country events get no value (missing, never zero). (3) Uncertainty: a block bootstrap over ISO weeks "
    "(1,000 resamples, fixed seed) gives a 90% interval for every BNN statistic. (4) Normalisation: indicators are "
    "min–max scaled to 0–100 on their theoretical scale, or the observed Asian range; skewed event rates are first "
    "log-transformed (log 1+x); lower-is-better indicators are inverted. (5) Category score = weighted mean of available "
    "indicators (≥50% of indicator weight required). Overall = weights 25/25/20/15/10/5 (Governance, Human Rights, "
    "Freedom & Democracy, Rule of Law, Press Freedom, Economic) re-weighted over enabled categories. (6) Missing data: a "
    "country needs ≥60% of total weight; a missing category is imputed with the LOWER of the country's own mean and the "
    "Asian median, so missing data can never raise a score. (7) Rank intervals: a Monte Carlo simulation (300 draws, "
    "fixed seed) redraws every statistic within its interval and recomputes all scores and ranks; the published score "
    "interval and best–worst rank are the 5th–95th percentiles. (8) Editorial adjustments: BNN editors may override a "
    "score, exclude a country or attach a note; every adjustment is published with its reason and the computed score. "
    "Verified international indices and BNN-verified incident records are combined with the event statistics. The index "
    "is recalculated and republished automatically every week; values are preliminary until the year ends.")
V2_LIMITATIONS = (
    "Event data is derived from news media and reflects what is reported, not ground truth: events that are not covered "
    "by the media are not counted. GDELT is machine-coded and contains classification errors (wrong actor types, "
    "duplicated stories, misplaced locations); aggregation over a year and rates per 1,000 events reduce but do not "
    "remove them. State-controlled or censored media environments under-report repression, which can make the most "
    "closed countries look better than they are; BNN mitigates this by combining event data with international indices "
    "and verified incidents and by editorial review, but cannot fully correct it. Intervals describe sampling variation "
    "over weeks, not coding error. Rankings are BNN Asia's own calculation and are not rankings of any source "
    "organisation.")

INCIDENT_INDICATOR_MAP = {
    "bnn_journalists_killed": ["journalist-killing"],
    "bnn_journalists_detained": ["journalist-arrest", "journalist-disappearance"],
    "bnn_fox_violations": ["freedom-of-expression-violation"],
    "bnn_disappearances": ["enforced-disappearance"],
    "bnn_killings_custody": ["extrajudicial-killing-allegation", "custodial-death"],
    "bnn_arbitrary_detention": ["arbitrary-arrest", "political-detention"],
    "bnn_torture": ["torture"],
}

V21_NOTE = (" Version 2.1.0 (November 2026) activates the Freedom & Democracy category: World Bank WGI Voice & "
            "Accountability and Political Stability (2026 edition) plus BNN's own protest-repression statistic. Reason: "
            "event data alone under-reports repression in closed media environments, so on its own it ranked several "
            "closed states too high; an independent measure of political rights and civil liberties corrects this.")

V22_NOTE = (" Version 2.2.0 (November 2026): in Human Rights and Press Freedom the event statistics are blended "
            "with an independent anchor, WGI Voice & Accountability (equal weight to the event block), because "
            "censored media report few abuses and event data alone ranked closed states highest; Political Stability "
            "is shown but no longer scored (stability is not democracy); the protest-repression share needs at least "
            "30 protest events, otherwise it is missing.")

WEIGHTS_2026 = {"good-governance": 25, "human-rights": 25, "freedom-democracy": 20, "rule-of-law": 15,
                "press-freedom": 10, "economic-social": 5}


class Command(BaseCommand):
    help = "Seed reference data and configuration (no scores)."

    @transaction.atomic
    def handle(self, *args, **opts):
        regions = {}
        for name, slug, parent, m49 in REGIONS:
            regions[slug], _ = Region.objects.update_or_create(
                slug=slug, defaults={"name": name, "parent": regions.get(parent), "un_m49_code": m49})
        for name, iso2, iso3, reg, cap, flag, aliases in COUNTRIES:
            Country.objects.update_or_create(iso3=iso3, defaults={
                "name": name, "slug": slugify(name), "iso2": iso2, "region": regions[reg], "capital": cap,
                "flag_emoji": flag, "aliases": aliases})
        ReportingPeriod.objects.get_or_create(slug="2026", defaults={
            "name": "2026", "start_date": dt.date(2026, 1, 1), "end_date": dt.date(2026, 12, 31),
            "status": "active", "is_current": True,
            "notes": "First edition. Only events dated 1 Jan–31 Dec 2026 count; index editions published in 2026 count."})
        cats = {}
        for slug, name, order, enabled, desc in CATEGORIES:
            c = IntelligenceCategory.objects.filter(slug=slug).first()
            if not c:
                c = IntelligenceCategory.objects.create(slug=slug, name=name, display_order=order, description=desc,
                                                        is_enabled=enabled, activation_date=dt.date(2026, 1, 1) if enabled else None)
            cats[slug] = c
        for name, cat in INCIDENT_TYPES:
            IncidentType.objects.get_or_create(slug=slugify(name), defaults={"name": name, "category": cats[cat]})
        srcs = {}
        for (name, slug, org, web, kind, method, endpoint, conn, cfg, rel, status, active, notes) in SOURCES:
            s, created = DataSource.objects.get_or_create(slug=slug, defaults=dict(
                name=name, organisation=org, website=web, kind=kind, method=method, endpoint=endpoint, connector=conn,
                config=cfg, reliability=rel, status=status, is_active=active, terms_notes=notes,
                sync_interval_hours=6 if method == "rss" else 168))
            if not created:
                s.config = cfg
                s.save(update_fields=["config"])
            srcs[slug] = s
        for i, (code, cat, name, unit, vt, direc, lo, hi, pc, scored, src, w) in enumerate(INDICATORS):
            Indicator.objects.update_or_create(code=code, defaults=dict(
                category=cats[cat], name=name, unit=unit, value_type=vt, direction=direc, scale_min=lo, scale_max=hi,
                per_capita=pc, used_in_scoring=scored, primary_source=srcs[src], weight_in_category=w, display_order=i,
                transform="log" if code in LOG_TRANSFORM else "none"))
        m, created = RankingMethodology.objects.get_or_create(
            name="BNN Asia Index", version="1.0.0", reporting_period=ReportingPeriod.objects.get(slug="2026"),
            defaults={"mode": "auto", "min_coverage": 0.6, "description": (
                "Weighted composite of six categories. Indicators are min–max normalised to 0–100 on their theoretical "
                "scale (or the observed Asian range for counts); lower-is-better indicators are inverted. Category scores "
                "are weighted means of available indicators. Missing categories are imputed with the lower of the "
                "country's own mean and the Asian median, so missing data can never raise a score."),
                "limitations": ("Counts of verified incidents reflect BNN monitoring capacity, which differs by country. "
                                "International indices describe the previous calendar year. Rankings are BNN Asia's own "
                                "calculation and are not rankings of the source organisations.")})
        if created:
            for slug, w in WEIGHTS_2026.items():
                MethodologyWeight.objects.create(methodology=m, category=cats[slug], weight=w)
        m2, created = RankingMethodology.objects.get_or_create(
            name="BNN Asia Index", version="2.0.0", reporting_period=ReportingPeriod.objects.get(slug="2026"),
            defaults={"mode": "auto", "min_coverage": 0.6, "description": V2_DESCRIPTION, "limitations": V2_LIMITATIONS})
        if created:
            for slug, w in WEIGHTS_2026.items():
                MethodologyWeight.objects.create(methodology=m2, category=cats[slug], weight=w)
        m21, created = RankingMethodology.objects.get_or_create(
            name="BNN Asia Index", version="2.1.0", reporting_period=ReportingPeriod.objects.get(slug="2026"),
            defaults={"mode": "auto", "min_coverage": 0.6, "description": V2_DESCRIPTION + V21_NOTE,
                      "limitations": V2_LIMITATIONS})
        if created:
            for slug, w in WEIGHTS_2026.items():
                MethodologyWeight.objects.create(methodology=m21, category=cats[slug], weight=w)
            # v2.1.0 activates Freedom & Democracy once; an admin who later switches it off is never overridden.
            IntelligenceCategory.objects.filter(slug="freedom-democracy", is_enabled=False,
                                                activation_date__isnull=True).update(
                is_enabled=True, activation_date=dt.date(2026, 1, 1))
        m22, created = RankingMethodology.objects.get_or_create(
            name="BNN Asia Index", version="2.2.0", reporting_period=ReportingPeriod.objects.get(slug="2026"),
            defaults={"mode": "auto", "min_coverage": 0.6, "description": V2_DESCRIPTION + V21_NOTE + V22_NOTE,
                      "limitations": V2_LIMITATIONS})
        if created:
            for slug, w in WEIGHTS_2026.items():
                MethodologyWeight.objects.create(methodology=m22, category=cats[slug], weight=w)
        self._groups()
        self.stdout.write(self.style.SUCCESS(
            f"Seeded {Country.objects.count()} countries, {IntelligenceCategory.objects.count()} categories, "
            f"{Indicator.objects.count()} indicators, {DataSource.objects.count()} sources."))

    def _groups(self):
        def perms(*models, actions=("view", "add", "change")):
            out = []
            for m in models:
                app, model = m.split(".")
                out += list(Permission.objects.filter(content_type__app_label=app, content_type__model=model,
                                                      codename__in=[f"{a}_{model}" for a in actions]))
            return out
        researcher, _ = Group.objects.get_or_create(name="Researcher")
        researcher.permissions.set(perms("incidents.newsarticle", "incidents.incident", "incidents.incidentclaim",
                                         "incidents.incidentevidence", "incidents.verificationtask",
                                         "observations.indicatorobservation", "reports.countryreport") +
                                   perms("core.country", "catalog.indicator", "catalog.intelligencecategory",
                                         "sources.datasource", "sources.datacollectionlog", "rankings.rankingsnapshot",
                                         "rankings.countryscore", actions=("view",)))
        editor, _ = Group.objects.get_or_create(name="Editor")
        editor.permissions.set(list(researcher.permissions.all()) + perms("incidents.incident", "reports.countryreport",
                                                                           actions=("view", "add", "change", "delete")))
