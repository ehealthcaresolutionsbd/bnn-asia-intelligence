# BNN Asia Index – methodology v1.0.0 (2026)

**Inputs.** Only *verified*, non-historical observations of the reporting period. Incident counts use only verified,
non-duplicate incidents whose **event date** is inside the period.

**Edition rule.** A value counts for 2026 if its reference period overlaps 2026, *or* the source edition was published
during 2026 (e.g. WGI 2025, released 25 Sep 2026). Everything else is stored as clearly-labelled historical reference and
never enters scores.

**Normalisation.** Min–max to 0–100 on the theoretical scale (WGI −2.5…+2.5, CPI/RSF 0…100) or the observed Asian range
for counts. Lower-is-better indicators are inverted. Per-capita indicators use World Bank population.

**Category score.** Weighted mean of available indicators; requires ≥50 % of the category's indicator weight.

**Overall.** Weights 25/25/20/15/10/5 (Governance, Human Rights, Freedom & Democracy, Rule of Law, Press Freedom,
Economic). Modes: *strict* (overall unavailable if a weighted category is off), *auto* (re-weight proportionally – default),
*custom*. Freedom & Democracy is disabled at launch, so auto mode re-weights over the remaining 80 %.

**Missing data.** Never zero. A country needs ≥60 % of total weight to be ranked, otherwise "Not Ranked – Insufficient
Data". Missing categories are imputed with the **lower** of the country's own mean and the Asian median, so missing data
can never raise a score; such countries cannot receive "high" confidence.

**Confidence.** high ≥90 % coverage and no imputation; medium ≥75 %; otherwise low.

**Publication.** Calculations create draft snapshots. Publishing freezes the snapshot and the methodology version;
changes require a new version. Previous published snapshots are kept ("superseded") for ranking history.

**Official vs BNN rankings.** Global ranks are shown exactly as published by the source. The "Asia position" column is
BNN Asia's re-ordering of Asian countries and is labelled as such.

# BNN Asia Index – methodology v2.0.0 (2026, data-driven)

v2 adds BNN Asia's **own statistics** computed from the GDELT 2.0 event database (`apps/signals`). v1.0.0 is unchanged.

**Signals.** Each GDELT event located in one of the 48 countries is classified by public rules (`apps/signals/rules.py`:
CAMEO code prefix + target/perpetrator actor types). Rules are served at `GET /api/v1/methodology/`.

**Indicators** (`apps/signals/indicators.py`, period start … last ingested day, lower is better):

| code | category | formula |
|---|---|---|
| bnn_sig_media_repression | Press Freedom | 1000 · media_repression / all in-country events |
| bnn_sig_censorship | Press Freedom | 1000 · censorship / all events |
| bnn_sig_state_repression | Human Rights | 1000 · state_repression / all events |
| bnn_sig_arrests | Human Rights | 1000 · arrests_detentions / all events |
| bnn_sig_violence | Human Rights | 1000 · killings_assaults / all events |
| bnn_sig_protest_repression | Freedom & Democracy | 100 · protest_repression / (protests + protest_repression) |

*Coverage correction:* dividing by all events in the same country/period removes the effect of unequal media attention.
Countries with < 300 in-country events get no value (missing, never zero). Values are *preliminary* until the period
ends, then *final*.

**Uncertainty.** 90 % interval per value by block bootstrap over ISO weeks (B = 1,000, seeded), widened to contain the
point estimate; stored as `ci_low`/`ci_high`, with `sample_size` = number of events in the denominator.

**Normalisation.** Event rates are skewed, so they are normalised on log(1 + x) over the observed Asian range
(`Indicator.transform = "log"`), then inverted.

**Rank intervals.** Monte Carlo, 300 seeded draws: every value with an interval is drawn from
N(value, (ci_high − ci_low)/3.29); categories, imputation and overall are recomputed per draw. `score_ci` = 5th–95th
percentile of the score, `rank_interval` = [best, worst] = 5th–95th percentile of the rank (both widened to contain
the published value).

**Editorial adjustments.** `override` replaces a category/overall score before ranking, `exclude` removes the country
from that ranking ("Excluded by editors"), `note` annotates. Every adjustment is public with its reason and the original
computed score (`editorial` in the API and CSV).

**Publication.** `refresh_index` (Celery: Mondays 04:00 UTC) rebuilds the signal and incident indicators, calculates v2
and publishes; previous snapshots become *superseded*. Open data: `GET /api/v1/ranking.csv[?category=slug]`.

**Limitations.** Media-based event data reflects reporting, not ground truth; GDELT machine coding contains errors;
state-controlled media environments under-report repression and can make closed countries look better.
