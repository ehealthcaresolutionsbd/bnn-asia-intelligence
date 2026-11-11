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
