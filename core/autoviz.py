"""Deterministic auto-visualization — no LLM, no rate limits.

Profiles the uploaded dataframe and renders a set of branded charts with
computed (pandas) insights. Chart choices follow the data's job: bar for
magnitude by category, line for change over time, histogram for
distribution, diverging heatmap for correlation. Single-series charts use
one brand hue; text stays in ink colors, never the series color.
"""

import time

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap

from core.analysis import AnalysisResult
from core.branding import ACCENT_COLOR, PRIMARY_COLOR
from core.settings import CHARTS_DIR

INK = "#23272e"
MUTED = "#6a707a"
GRID = "#e3e5e8"

MAX_BARS = 10
VALUE_KEYWORDS = (
    "revenue", "sales", "amount", "total", "price", "profit", "income",
    "cost", "value", "qty", "quantity", "count", "units",
)


def _style_axes(ax) -> None:
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=9)
    ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    ax.xaxis.grid(False)
    ax.set_axisbelow(True)


def _new_figure(title: str):
    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=150)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    ax.set_title(title, loc="left", fontsize=12, fontweight="bold", color=INK, pad=12)
    _style_axes(ax)
    return fig, ax


def _save(fig) -> str:
    path = CHARTS_DIR / f"autoviz_{int(time.time() * 1000)}_{np.random.randint(1e6)}.png"
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return str(path)


def _fmt(value: float) -> str:
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:,.1f}M"
    if abs(value) >= 1_000:
        return f"{value / 1_000:,.1f}K"
    if abs(value) >= 100 or float(value).is_integer():
        return f"{value:,.0f}"
    return f"{value:,.2f}"


def _profile(df: pd.DataFrame):
    """Split columns into numeric / categorical / datetime."""
    numeric, categorical, datetime_cols = [], [], []
    for col in df.columns:
        series = df[col]
        if pd.api.types.is_numeric_dtype(series):
            if series.nunique(dropna=True) > 1:
                numeric.append(col)
        elif pd.api.types.is_datetime64_any_dtype(series):
            datetime_cols.append(col)
        else:
            parsed = pd.to_datetime(series, errors="coerce", format="mixed")
            if parsed.notna().mean() > 0.9 and parsed.nunique() > 3:
                datetime_cols.append(col)
            elif 2 <= series.nunique(dropna=True) <= 30:
                categorical.append(col)
    return numeric, categorical, datetime_cols


def _pick_value_column(numeric: list[str]) -> str | None:
    for keyword in VALUE_KEYWORDS:
        for col in numeric:
            if keyword in col.lower():
                return col
    return numeric[0] if numeric else None


def _bar_by_category(df, cat_col, val_col) -> AnalysisResult:
    totals = df.groupby(cat_col)[val_col].sum().sort_values(ascending=False)
    shown = totals.head(MAX_BARS)
    fig, ax = _new_figure(f"{val_col} by {cat_col}")

    colors = [PRIMARY_COLOR] * len(shown)
    colors[0] = ACCENT_COLOR  # highlight the leader
    positions = np.arange(len(shown))
    ax.barh(positions, shown.values, height=0.62, color=colors)
    ax.set_yticks(positions, [str(v) for v in shown.index])
    ax.invert_yaxis()
    ax.xaxis.grid(True, color=GRID, linewidth=0.8)
    ax.yaxis.grid(False)
    for pos, value in zip(positions, shown.values):
        ax.text(value, pos, f" {_fmt(value)}", va="center", fontsize=8.5, color=MUTED)

    top_name, top_value = shown.index[0], shown.iloc[0]
    share = top_value / totals.sum() * 100 if totals.sum() else 0
    note = f" (top {MAX_BARS} of {len(totals)} shown)" if len(totals) > MAX_BARS else ""
    insight = (
        f"{top_name} leads with {_fmt(top_value)} — {share:.1f}% of all "
        f"{val_col} across {len(totals)} {cat_col} groups{note}."
    )
    return AnalysisResult(
        question=f"{val_col} by {cat_col}", kind="chart",
        text=insight, chart_path=_save(fig),
    )


def _trend_over_time(df, date_col, val_col) -> AnalysisResult | None:
    dates = pd.to_datetime(df[date_col], errors="coerce", format="mixed")
    frame = pd.DataFrame({date_col: dates, val_col: df[val_col]}).dropna()
    if frame.empty:
        return None
    span_days = (frame[date_col].max() - frame[date_col].min()).days
    freq, unit = ("MS", "monthly") if span_days > 92 else ("D", "daily")
    series = frame.set_index(date_col)[val_col].resample(freq).sum()
    series = series[series != 0].dropna()
    if len(series) < 3:
        return None

    fig, ax = _new_figure(f"{val_col} over time ({unit})")
    ax.plot(series.index, series.values, color=PRIMARY_COLOR, linewidth=2)
    ax.plot(series.index[-1], series.iloc[-1], "o", color=ACCENT_COLOR, markersize=8)
    ax.annotate(
        _fmt(series.iloc[-1]), (series.index[-1], series.iloc[-1]),
        textcoords="offset points", xytext=(6, 6), fontsize=8.5, color=MUTED,
    )
    fig.autofmt_xdate(rotation=0, ha="center")

    first, last = series.iloc[0], series.iloc[-1]
    change = (last - first) / abs(first) * 100 if first else 0
    direction = "up" if change > 0 else "down"
    peak_at = series.idxmax()
    insight = (
        f"{val_col} moved {direction} {abs(change):.1f}% across the period "
        f"({_fmt(first)} → {_fmt(last)}), peaking at {_fmt(series.max())} "
        f"in {peak_at:%b %Y}."
    )
    return AnalysisResult(
        question=f"{val_col} trend over time", kind="chart",
        text=insight, chart_path=_save(fig),
    )


def _distribution(df, val_col) -> AnalysisResult:
    values = df[val_col].dropna()
    fig, ax = _new_figure(f"Distribution of {val_col}")
    ax.hist(values, bins=min(30, max(10, int(np.sqrt(len(values))))),
            color=PRIMARY_COLOR, edgecolor="white", linewidth=0.8)
    ax.axvline(values.median(), color=ACCENT_COLOR, linewidth=2)
    ax.annotate(
        f"median {_fmt(values.median())}", (values.median(), ax.get_ylim()[1]),
        textcoords="offset points", xytext=(6, -12), fontsize=8.5, color=MUTED,
    )
    insight = (
        f"{val_col} ranges {_fmt(values.min())}–{_fmt(values.max())} with a "
        f"median of {_fmt(values.median())} and mean of {_fmt(values.mean())} "
        f"across {len(values):,} records."
    )
    return AnalysisResult(
        question=f"Distribution of {val_col}", kind="chart",
        text=insight, chart_path=_save(fig),
    )


def _correlation(df, numeric) -> AnalysisResult | None:
    cols = numeric[:8]
    corr = df[cols].corr()
    if corr.isna().all().all():
        return None
    # diverging: gold (negative) -> neutral -> navy (positive)
    cmap = LinearSegmentedColormap.from_list(
        "brand_div", [ACCENT_COLOR, "#f2f2f0", PRIMARY_COLOR]
    )
    fig, ax = plt.subplots(figsize=(7, 6), dpi=150)
    fig.patch.set_facecolor("white")
    ax.set_title("Correlation between numeric columns", loc="left",
                 fontsize=12, fontweight="bold", color=INK, pad=12)
    image = ax.imshow(corr.values, cmap=cmap, vmin=-1, vmax=1)
    ax.set_xticks(range(len(cols)), cols, rotation=35, ha="right", fontsize=8.5, color=MUTED)
    ax.set_yticks(range(len(cols)), cols, fontsize=8.5, color=MUTED)
    for i in range(len(cols)):
        for j in range(len(cols)):
            value = corr.values[i, j]
            text_color = "white" if abs(value) > 0.6 else INK
            ax.text(j, i, f"{value:.2f}", ha="center", va="center",
                    fontsize=8, color=text_color)
    fig.colorbar(image, shrink=0.75).ax.tick_params(labelsize=8, colors=MUTED)

    pairs = corr.where(~np.eye(len(cols), dtype=bool)).abs().unstack().dropna()
    if pairs.empty:
        return None
    (col_a, col_b) = pairs.idxmax()
    strongest = corr.loc[col_a, col_b]
    kind_word = "positively" if strongest > 0 else "negatively"
    insight = (
        f"The strongest relationship is between {col_a} and {col_b} "
        f"({strongest:+.2f}), which move {kind_word} together."
    )
    return AnalysisResult(
        question="Correlation between numeric columns", kind="chart",
        text=insight, chart_path=_save(fig),
    )


def auto_visualize(df: pd.DataFrame, max_charts: int = 6) -> list[AnalysisResult]:
    """Build a standard set of branded charts + computed insights, LLM-free."""
    numeric, categorical, datetime_cols = _profile(df)
    val_col = _pick_value_column(numeric)
    results: list[AnalysisResult] = []

    if val_col and datetime_cols:
        trend = _trend_over_time(df, datetime_cols[0], val_col)
        if trend:
            results.append(trend)
    if val_col:
        for cat_col in categorical[:3]:
            results.append(_bar_by_category(df, cat_col, val_col))
    if val_col:
        results.append(_distribution(df, val_col))
    if len(numeric) >= 3:
        heatmap = _correlation(df, numeric)
        if heatmap:
            results.append(heatmap)

    if not results:
        return [AnalysisResult(
            question="Auto-visualization", kind="error",
            text="No suitable numeric/categorical columns found to chart automatically.",
        )]
    return results[:max_charts]
