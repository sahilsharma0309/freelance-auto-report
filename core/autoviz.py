"""Deterministic auto-visualization — no LLM, no rate limits.

Profiles the uploaded dataframe and builds interactive plotly charts
(hover, zoom in the app) with computed pandas insights; each figure is
also rendered to PNG for the PDF/Word reports. Chart choices follow the
data's job: line for change over time, bars for magnitude by category,
histogram for distribution, diverging colors only for polarity
(correlation, growth vs decline). Single-series charts use one brand
hue; text stays in ink colors.
"""

import time

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from core.analysis import AnalysisResult
from core.branding import ACCENT_COLOR, PRIMARY_COLOR, SERIES_PALETTE
from core.settings import CHARTS_DIR

INK = "#23272e"
MUTED = "#6a707a"
GRID = "#e8eaed"
NEUTRAL_MID = "#f2f2f0"

MAX_BARS = 10
VALUE_KEYWORDS = (
    "revenue", "sales", "amount", "total", "price", "profit", "income",
    "cost", "value", "qty", "quantity", "count", "units",
)

_AXIS = dict(
    gridcolor=GRID, zeroline=False, linecolor=GRID,
    tickfont=dict(color=MUTED, size=12), title=None,
)

_LAYOUT = dict(
    font=dict(family="Helvetica, Arial, sans-serif", color=INK, size=13),
    paper_bgcolor="white", plot_bgcolor="white",
    margin=dict(l=70, r=40, t=70, b=60),
    hoverlabel=dict(bgcolor=PRIMARY_COLOR, font=dict(color="white", size=12)),
    showlegend=False,
)


def _base_figure(title: str) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(
        title=dict(text=f"<b>{title}</b>", x=0.01, font=dict(size=17, color=INK)),
        xaxis=_AXIS, yaxis=_AXIS, **_LAYOUT,
    )
    return fig


def _save(fig: go.Figure) -> str:
    path = CHARTS_DIR / f"autoviz_{int(time.time() * 1000)}_{np.random.randint(1e6)}.png"
    fig.write_image(str(path), width=1000, height=560, scale=2)
    return str(path)


def _result(title: str, fig: go.Figure, insight: str) -> AnalysisResult:
    return AnalysisResult(
        question=title, kind="chart", text=insight,
        chart_path=_save(fig), figure=fig,
    )


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


def _monthly_series(df, date_col, val_col) -> pd.Series | None:
    dates = pd.to_datetime(df[date_col], errors="coerce", format="mixed")
    frame = pd.DataFrame({"d": dates, "v": df[val_col]}).dropna()
    if frame.empty:
        return None
    span_days = (frame["d"].max() - frame["d"].min()).days
    freq = "MS" if span_days > 92 else "D"
    series = frame.set_index("d")["v"].resample(freq).sum()
    series = series[series != 0].dropna()
    return series if len(series) >= 3 else None


def _trend_over_time(df, date_col, val_col) -> AnalysisResult | None:
    series = _monthly_series(df, date_col, val_col)
    if series is None:
        return None
    unit = "monthly" if series.index.freqstr in ("MS",) else "daily"
    title = f"{val_col} over time ({unit})"
    fig = _base_figure(title)
    fig.add_trace(go.Scatter(
        x=series.index, y=series.values, mode="lines",
        line=dict(color=PRIMARY_COLOR, width=2.5),
        hovertemplate="%{x|%b %Y}: <b>%{y:,.0f}</b><extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=[series.index[-1]], y=[series.iloc[-1]], mode="markers+text",
        marker=dict(color=ACCENT_COLOR, size=11),
        text=[_fmt(series.iloc[-1])], textposition="top left",
        textfont=dict(color=MUTED, size=12), hoverinfo="skip",
    ))
    fig.update_xaxes(hoverformat="%b %Y")

    first, last = series.iloc[0], series.iloc[-1]
    change = (last - first) / abs(first) * 100 if first else 0
    direction = "up" if change > 0 else "down"
    insight = (
        f"{val_col} moved {direction} {abs(change):.1f}% across the period "
        f"({_fmt(first)} → {_fmt(last)}), peaking at {_fmt(series.max())} "
        f"in {series.idxmax():%b %Y}."
    )
    return _result(title, fig, insight)


def _growth_by_period(df, date_col, val_col) -> AnalysisResult | None:
    """Period-over-period growth bars — diverging by polarity only."""
    series = _monthly_series(df, date_col, val_col)
    if series is None or series.index.freqstr != "MS" or len(series) < 4:
        return None
    growth = series.pct_change().dropna() * 100
    title = f"{val_col} month-over-month growth %"
    fig = _base_figure(title)
    colors = [PRIMARY_COLOR if v >= 0 else ACCENT_COLOR for v in growth.values]
    fig.add_trace(go.Bar(
        x=growth.index, y=growth.values, marker_color=colors,
        hovertemplate="%{x|%b %Y}: <b>%{y:+.1f}%</b><extra></extra>",
    ))
    fig.add_hline(y=0, line_color=GRID, line_width=1)
    fig.update_yaxes(ticksuffix="%")

    ups = int((growth > 0).sum())
    best = growth.idxmax()
    worst = growth.idxmin()
    insight = (
        f"{ups} of {len(growth)} months grew (navy = growth, gold = decline). "
        f"Best month: {best:%b %Y} ({growth.max():+.1f}%); "
        f"toughest: {worst:%b %Y} ({growth.min():+.1f}%)."
    )
    return _result(title, fig, insight)


def _trend_by_category(df, date_col, val_col, cat_col) -> AnalysisResult | None:
    """Multi-series comparison: monthly value split across top categories."""
    top = df.groupby(cat_col)[val_col].sum().nlargest(len(SERIES_PALETTE)).index.tolist()
    dates = pd.to_datetime(df[date_col], errors="coerce", format="mixed")
    frame = pd.DataFrame({
        "d": dates, "v": df[val_col], "c": df[cat_col].astype(str),
    }).dropna()
    frame = frame[frame["c"].isin([str(t) for t in top])]
    if frame.empty or (frame["d"].max() - frame["d"].min()).days <= 92:
        return None
    pivot = (
        frame.set_index("d").groupby("c").resample("MS")["v"].sum()
        .unstack(level=0).fillna(0)
    )
    if len(pivot) < 3:
        return None
    pivot = pivot[[str(t) for t in top if str(t) in pivot.columns]]

    title = f"{val_col} by {cat_col} over time (top {len(pivot.columns)})"
    fig = _base_figure(title)
    for idx, col in enumerate(pivot.columns):
        color = SERIES_PALETTE[idx]
        fig.add_trace(go.Scatter(
            x=pivot.index, y=pivot[col], mode="lines", name=col,
            line=dict(color=color, width=2.5),
            hovertemplate=f"{col} · %{{x|%b %Y}}: <b>%{{y:,.0f}}</b><extra></extra>",
        ))
        fig.add_annotation(  # direct label at the line's end
            x=pivot.index[-1], y=pivot[col].iloc[-1], text=f" {col}",
            showarrow=False, xanchor="left", font=dict(color=color, size=12),
        )
    fig.update_layout(
        showlegend=True,
        legend=dict(orientation="h", y=1.08, x=0, font=dict(color=MUTED)),
        margin=dict(l=70, r=110, t=90, b=60),
    )

    growth = {
        col: (pivot[col].iloc[-1] - pivot[col].iloc[0]) / abs(pivot[col].iloc[0]) * 100
        for col in pivot.columns if pivot[col].iloc[0]
    }
    insight = f"Comparing the top {len(pivot.columns)} {cat_col} groups by {val_col}."
    if growth:
        fastest = max(growth, key=growth.get)
        insight += (
            f" {fastest} grew fastest across the period ({growth[fastest]:+.1f}%), "
            f"while {min(growth, key=growth.get)} moved "
            f"{growth[min(growth, key=growth.get)]:+.1f}%."
        )
    return _result(title, fig, insight)


def _bar_by_category(df, cat_col, val_col) -> AnalysisResult:
    totals = df.groupby(cat_col)[val_col].sum().sort_values(ascending=False)
    shown = totals.head(MAX_BARS).iloc[::-1]  # reversed for horizontal layout
    title = f"{val_col} by {cat_col}"
    fig = _base_figure(title)
    colors = [PRIMARY_COLOR] * len(shown)
    colors[-1] = ACCENT_COLOR  # leader sits at the top after reversal
    fig.add_trace(go.Bar(
        x=shown.values, y=[str(v) for v in shown.index], orientation="h",
        marker_color=colors, text=[_fmt(v) for v in shown.values],
        textposition="outside", textfont=dict(color=MUTED, size=12),
        hovertemplate="%{y}: <b>%{x:,.0f}</b><extra></extra>",
    ))
    fig.update_xaxes(showgrid=True)
    fig.update_yaxes(showgrid=False)

    top_name, top_value = totals.index[0], totals.iloc[0]
    share = top_value / totals.sum() * 100 if totals.sum() else 0
    note = f" (top {MAX_BARS} of {len(totals)} shown)" if len(totals) > MAX_BARS else ""
    insight = (
        f"{top_name} leads with {_fmt(top_value)} — {share:.1f}% of all "
        f"{val_col} across {len(totals)} {cat_col} groups{note}."
    )
    return _result(title, fig, insight)


def _distribution(df, val_col) -> AnalysisResult:
    values = df[val_col].dropna()
    title = f"Distribution of {val_col}"
    fig = _base_figure(title)
    fig.add_trace(go.Histogram(
        x=values, nbinsx=min(30, max(10, int(np.sqrt(len(values))))),
        marker=dict(color=PRIMARY_COLOR, line=dict(color="white", width=1)),
        hovertemplate="%{x}: <b>%{y}</b> records<extra></extra>",
    ))
    fig.add_vline(
        x=float(values.median()), line_color=ACCENT_COLOR, line_width=2,
        annotation_text=f"median {_fmt(values.median())}",
        annotation_font=dict(color=MUTED, size=12),
    )
    insight = (
        f"{val_col} ranges {_fmt(values.min())}–{_fmt(values.max())} with a "
        f"median of {_fmt(values.median())} and mean of {_fmt(values.mean())} "
        f"across {len(values):,} records."
    )
    return _result(title, fig, insight)


def _correlation(df, numeric) -> AnalysisResult | None:
    cols = numeric[:8]
    corr = df[cols].corr()
    if corr.isna().all().all():
        return None
    title = "Correlation between numeric columns"
    fig = _base_figure(title)
    fig.add_trace(go.Heatmap(
        z=corr.values, x=cols, y=cols, zmin=-1, zmax=1,
        colorscale=[[0.0, ACCENT_COLOR], [0.5, NEUTRAL_MID], [1.0, PRIMARY_COLOR]],
        text=np.round(corr.values, 2), texttemplate="%{text:.2f}",
        textfont=dict(size=11),
        hovertemplate="%{y} × %{x}: <b>%{z:.2f}</b><extra></extra>",
        colorbar=dict(tickfont=dict(color=MUTED)),
    ))
    fig.update_layout(height=520)

    pairs = corr.where(~np.eye(len(cols), dtype=bool)).abs().unstack().dropna()
    if pairs.empty:
        return None
    (col_a, col_b) = pairs.idxmax()
    strongest = corr.loc[col_a, col_b]
    kind_word = "positively" if strongest > 0 else "negatively"
    insight = (
        f"The strongest relationship is between {col_a} and {col_b} "
        f"({strongest:+.2f}), which move {kind_word} together "
        f"(navy = positive, gold = negative)."
    )
    return _result(title, fig, insight)


def auto_visualize(df: pd.DataFrame, max_charts: int = 8) -> list[AnalysisResult]:
    """Build a dashboard-style chart set + computed insights, LLM-free."""
    numeric, categorical, datetime_cols = _profile(df)
    val_col = _pick_value_column(numeric)
    results: list[AnalysisResult] = []

    if val_col and datetime_cols:
        for builder in (_trend_over_time, _growth_by_period):
            chart = builder(df, datetime_cols[0], val_col)
            if chart:
                results.append(chart)
        if categorical:
            comparison = _trend_by_category(df, datetime_cols[0], val_col, categorical[0])
            if comparison:
                results.append(comparison)
    if val_col:
        for cat_col in categorical[:3]:
            results.append(_bar_by_category(df, cat_col, val_col))
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
