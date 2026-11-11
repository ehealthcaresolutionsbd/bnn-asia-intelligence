"""Static PNG charts for country reports (matplotlib, Agg backend).

Every chart is drawn only from numbers the builder already computed from the database;
nothing here queries data. Figures are always closed to keep batch generation fast.
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from django.conf import settings  # noqa: E402

RED, INK, GREY, LIGHT = "#C8102E", "#0E1116", "#6B7280", "#D1D5DB"
LINE_COLOURS = [RED, INK, GREY, "#E8919F"]
LINE_STYLES = ["-", "-", "--", ":"]
CHART_DIR = "reports/charts"

_available = {f.name for f in font_manager.fontManager.ttflist}
_FONT = [f for f in ("Manrope", "DejaVu Sans") if f in _available] or ["sans-serif"]
STYLE = {
    "font.family": "sans-serif", "font.sans-serif": _FONT, "font.size": 8.5,
    "axes.edgecolor": LIGHT, "axes.labelcolor": INK, "axes.titlesize": 10, "axes.titleweight": "bold",
    "axes.titlecolor": INK, "axes.titlelocation": "left", "axes.spines.top": False, "axes.spines.right": False,
    "xtick.color": GREY, "ytick.color": GREY, "grid.color": "#EEF0F3", "grid.linewidth": 0.8,
    "legend.frameon": False, "figure.dpi": 100, "savefig.dpi": 160, "savefig.bbox": "tight",
}


def chart_dir() -> Path:
    d = Path(settings.MEDIA_ROOT) / CHART_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def _save(fig, name):
    path = chart_dir() / name
    fig.savefig(path, facecolor="white")
    plt.close(fig)
    return f"{CHART_DIR}/{name}"


def trend_chart(name, months, series, country_name):
    """months: ['2026-01', …]; series: [(label, [rate or None per month])]. Returns relative path."""
    with plt.rc_context(STYLE):
        fig, ax = plt.subplots(figsize=(7.2, 3.0))
        x = list(range(len(months)))
        for i, (label, values) in enumerate(series):
            ax.plot(x, [v if v is not None else float("nan") for v in values], LINE_STYLES[i % 4],
                    color=LINE_COLOURS[i % 4], linewidth=1.8, marker="o", markersize=3, label=label)
        ax.set_xticks(x, [_month_label(m) for m in months])
        ax.set_ylabel("Events per 1,000 in-country events")
        ax.set_ylim(bottom=0)
        ax.grid(axis="y")
        ax.set_title(f"{country_name}: monthly event-data signals")
        ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.14), ncol=2, fontsize=7.5)
        return _save(fig, name)


def category_chart(name, rows, country_name):
    """rows: [(category name, country score, asian median)] – scores 0–100."""
    with plt.rc_context(STYLE):
        fig, ax = plt.subplots(figsize=(7.2, 0.5 + 0.42 * len(rows)))
        y = list(range(len(rows)))[::-1]
        ax.barh(y, [r[1] for r in rows], height=0.55, color=RED, label=country_name, zorder=2)
        meds = [(yy, r[2]) for yy, r in zip(y, rows) if r[2] is not None]
        if meds:
            ax.scatter([m[1] for m in meds], [m[0] for m in meds], marker="|", s=260, linewidths=2.2,
                       color=INK, zorder=3, label="Asian median")
        for yy, r in zip(y, rows):
            ax.text(r[1] + 1.2, yy, f"{r[1]:.1f}", va="center", fontsize=7.5, color=INK)
        ax.set_yticks(y, [r[0] for r in rows])
        ax.set_xlim(0, 105)
        ax.set_xlabel("Category score (0–100, higher is better)")
        ax.grid(axis="x", zorder=0)
        ax.set_title("Category scores compared with the Asian median")
        ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.5 / max(len(rows), 1) - 0.18), ncol=2, fontsize=7.5)
        return _save(fig, name)


def position_chart(name, scores, highlight_iso3, median):
    """scores: [(iso3, score)] for all ranked Asian countries."""
    pts = sorted(scores, key=lambda t: -t[1])
    with plt.rc_context(STYLE):
        fig, ax = plt.subplots(figsize=(7.2, 2.7))
        x = list(range(1, len(pts) + 1))
        colours = [RED if iso == highlight_iso3 else GREY for iso, _ in pts]
        sizes = [46 if iso == highlight_iso3 else 16 for iso, _ in pts]
        ax.scatter(x, [s for _, s in pts], c=colours, s=sizes, zorder=3)
        for xx, (iso, s) in zip(x, pts):
            if iso == highlight_iso3:
                ax.annotate(f"{iso} {s:.1f}", (xx, s), xytext=(0, 9), textcoords="offset points", ha="center",
                            fontsize=8, fontweight="bold", color=RED)
        if median is not None:
            ax.axhline(median, color=INK, linewidth=0.9, linestyle="--", zorder=2)
            ax.text(len(pts) + 0.4, median, f"median {median:.1f}", va="bottom", ha="right", fontsize=7, color=INK)
        ax.set_xlabel("Rank among ranked Asian countries (1 = highest score)")
        ax.set_ylabel("BNN Asia Index score")
        ax.set_xlim(0, len(pts) + 1)
        ax.grid(axis="y")
        ax.set_title("Position among Asian countries – overall BNN Asia Index")
        return _save(fig, name)


def _month_label(m):
    import calendar
    y, mm = m.split("-")
    return f"{calendar.month_abbr[int(mm)]}\n{y}" if mm == "01" else calendar.month_abbr[int(mm)]
