"""Deterministic auto-visualization — no LLM, no rate limits.

Profiles the uploaded dataframe and builds interactive plotly charts
(hover, zoom in the app) with computed pandas insights; each figure is
also rendered to PNG for the PDF/Word reports. All titles, insights and
reading guides are written in the selected language (core.i18n).
"""

import time

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from core.analysis import AnalysisResult
from core.branding import (
    ACCENT_COLOR,
    CATEGORICAL_PALETTE,
    PRIMARY_COLOR,
    SERIES_PALETTE,
)
from core.i18n import t
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

FONT_STACK = "Helvetica, Arial, 'Noto Sans Devanagari', 'Noto Sans', sans-serif"

_AXIS = dict(
    gridcolor=GRID, zeroline=False, linecolor=GRID,
    tickfont=dict(color=MUTED, size=12), title=None,
)

_LAYOUT = dict(
    font=dict(family=FONT_STACK, color=INK, size=13),
    paper_bgcolor="white", plot_bgcolor="white",
    margin=dict(l=70, r=40, t=70, b=60),
    hoverlabel=dict(bgcolor=PRIMARY_COLOR, font=dict(color="white", size=12)),
    showlegend=False,
    barcornerradius=5,
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


def _result(title: str, fig: go.Figure, insight: str,
            guide: str = "", priority: int = 5) -> AnalysisResult:
    return AnalysisResult(
        question=title, kind="chart", text=insight,
        chart_path=_save(fig), figure=fig,
        guide=guide, priority=priority,
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


def _hex_to_rgba(color: str, alpha: float) -> str:
    color = color.lstrip("#")
    r, g, b = (int(color[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


def _trend_over_time(df, date_col, val_col, lang="en") -> AnalysisResult | None:
    series = _monthly_series(df, date_col, val_col)
    if series is None:
        return None
    unit = t("unit_monthly" if series.index.freqstr == "MS" else "unit_daily", lang)
    title = t("title_trend", lang).format(col=val_col, unit=unit)
    fig = _base_figure(title)
    fig.add_trace(go.Scatter(
        x=series.index, y=series.values, mode="lines",
        line=dict(color=PRIMARY_COLOR, width=2.5),
        fill="tozeroy", fillcolor=_hex_to_rgba(PRIMARY_COLOR, 0.07),
        hovertemplate="%{x|%b %Y}: <b>%{y:,.0f}</b><extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=[series.index[-1]], y=[series.iloc[-1]], mode="markers+text",
        marker=dict(color=ACCENT_COLOR, size=11),
        text=[_fmt(series.iloc[-1])], textposition="top left",
        textfont=dict(color=MUTED, size=12), hoverinfo="skip",
    ))

    first, last = series.iloc[0], series.iloc[-1]
    change = (last - first) / abs(first) * 100 if first else 0
    insight = t("ins_trend", lang).format(
        col=val_col, direction=t("up" if change > 0 else "down", lang),
        change=abs(change), first=_fmt(first), last=_fmt(last),
        peak=_fmt(series.max()), peak_month=f"{series.idxmax():%b %Y}",
    )
    return _result(title, fig, insight, t("guide_trend", lang), priority=1)


def _growth_by_period(df, date_col, val_col, lang="en") -> AnalysisResult | None:
    series = _monthly_series(df, date_col, val_col)
    if series is None or series.index.freqstr != "MS" or len(series) < 4:
        return None
    growth = series.pct_change().dropna() * 100
    title = t("title_growth", lang).format(col=val_col)
    fig = _base_figure(title)
    colors = [PRIMARY_COLOR if v >= 0 else ACCENT_COLOR for v in growth.values]
    fig.add_trace(go.Bar(
        x=growth.index, y=growth.values, marker_color=colors,
        hovertemplate="%{x|%b %Y}: <b>%{y:+.1f}%</b><extra></extra>",
    ))
    fig.add_hline(y=0, line_color=GRID, line_width=1)
    fig.update_yaxes(ticksuffix="%")

    insight = t("ins_growth", lang).format(
        ups=int((growth > 0).sum()), total=len(growth),
        best=f"{growth.idxmax():%b %Y}", best_pct=growth.max(),
        worst=f"{growth.idxmin():%b %Y}", worst_pct=growth.min(),
    )
    return _result(title, fig, insight, t("guide_growth", lang), priority=2)


def _trend_by_category(df, date_col, val_col, cat_col, lang="en") -> AnalysisResult | None:
    """Multi-series comparison: monthly value split across top categories."""
    top = df.groupby(cat_col)[val_col].sum().nlargest(len(SERIES_PALETTE)).index.tolist()
    dates = pd.to_datetime(df[date_col], errors="coerce", format="mixed")
    frame = pd.DataFrame({
        "d": dates, "v": df[val_col], "c": df[cat_col].astype(str),
    }).dropna()
    frame = frame[frame["c"].isin([str(x) for x in top])]
    if frame.empty or (frame["d"].max() - frame["d"].min()).days <= 92:
        return None
    pivot = (
        frame.set_index("d").groupby("c").resample("MS")["v"].sum()
        .unstack(level=0).fillna(0)
    )
    if len(pivot) < 3:
        return None
    pivot = pivot[[str(x) for x in top if str(x) in pivot.columns]]

    title = t("title_comparison", lang).format(col=val_col, cat=cat_col, n=len(pivot.columns))
    fig = _base_figure(title)
    for idx, col in enumerate(pivot.columns):
        color = SERIES_PALETTE[idx]
        fig.add_trace(go.Scatter(
            x=pivot.index, y=pivot[col], mode="lines", name=col,
            line=dict(color=color, width=2.5),
            hovertemplate=f"{col} · %{{x|%b %Y}}: <b>%{{y:,.0f}}</b><extra></extra>",
        ))
        fig.add_annotation(
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
    insight = t("ins_comparison", lang).format(n=len(pivot.columns), cat=cat_col, col=val_col)
    if growth:
        fastest = max(growth, key=growth.get)
        slowest = min(growth, key=growth.get)
        insight += t("ins_comparison_growth", lang).format(
            fastest=fastest, fastest_pct=growth[fastest],
            slowest=slowest, slowest_pct=growth[slowest],
        )
    return _result(title, fig, insight, t("guide_comparison", lang), priority=3)


def _month_category_heatmap(df, date_col, val_col, cat_col, lang="en") -> AnalysisResult | None:
    dates = pd.to_datetime(df[date_col], errors="coerce", format="mixed")
    frame = pd.DataFrame({
        "d": dates, "v": df[val_col], "c": df[cat_col].astype(str),
    }).dropna()
    if frame.empty or (frame["d"].max() - frame["d"].min()).days <= 92:
        return None
    top = frame.groupby("c")["v"].sum().nlargest(8).index
    frame = frame[frame["c"].isin(top)]
    frame["month"] = frame["d"].dt.to_period("M").dt.to_timestamp()
    pivot = frame.pivot_table(index="c", columns="month", values="v", aggfunc="sum").fillna(0)
    if pivot.shape[1] < 3:
        return None
    pivot = pivot.loc[pivot.sum(axis=1).sort_values().index]

    title = t("title_heatmap", lang).format(col=val_col, cat=cat_col)
    fig = _base_figure(title)
    fig.add_trace(go.Heatmap(
        z=pivot.values, x=[f"{m:%b %y}" for m in pivot.columns], y=list(pivot.index),
        colorscale=[[0.0, "#f6f7f9"], [1.0, PRIMARY_COLOR]],
        hovertemplate="%{y} · %{x}: <b>%{z:,.0f}</b><extra></extra>",
        colorbar=dict(tickfont=dict(color=MUTED)),
    ))
    fig.update_layout(height=max(380, 60 * len(pivot) + 160))

    best_row, best_col = np.unravel_index(np.argmax(pivot.values), pivot.values.shape)
    insight = t("ins_heatmap", lang).format(
        cat=pivot.index[best_row], month=f"{pivot.columns[best_col]:%B %Y}",
        value=_fmt(pivot.values[best_row, best_col]),
    )
    guide = t("guide_heatmap", lang).format(cat=cat_col)
    return _result(title, fig, insight, guide, priority=4)


def _weekday_pattern(df, date_col, val_col, lang="en") -> AnalysisResult | None:
    dates = pd.to_datetime(df[date_col], errors="coerce", format="mixed")
    frame = pd.DataFrame({"d": dates, "v": df[val_col]}).dropna()
    if frame.empty or frame["d"].dt.date.nunique() < 14:
        return None
    daily = frame.groupby(frame["d"].dt.date)["v"].sum()
    weekdays = pd.to_datetime(pd.Series(daily.index)).dt.day_name()
    order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    averages = daily.groupby(weekdays.values).mean().reindex(order).dropna()
    if len(averages) < 5:
        return None

    title = t("title_weekday", lang).format(col=val_col)
    fig = _base_figure(title)
    colors = [ACCENT_COLOR if day == averages.idxmax() else PRIMARY_COLOR
              for day in averages.index]
    fig.add_trace(go.Bar(
        x=list(averages.index), y=averages.values, marker_color=colors,
        text=[_fmt(v) for v in averages.values], textposition="outside",
        textfont=dict(color=MUTED, size=11),
        hovertemplate="%{x}: <b>%{y:,.0f}</b><extra></extra>",
    ))

    insight = t("ins_weekday", lang).format(
        best=averages.idxmax(), best_val=_fmt(averages.max()),
        worst=averages.idxmin(), worst_val=_fmt(averages.min()),
    )
    return _result(title, fig, insight, t("guide_weekday", lang), priority=5)


def _bar_by_category(df, cat_col, val_col, lang="en") -> AnalysisResult:
    totals = df.groupby(cat_col)[val_col].sum().sort_values(ascending=False)
    shown = totals.head(MAX_BARS).iloc[::-1]
    title = t("title_bar", lang).format(col=val_col, cat=cat_col)
    fig = _base_figure(title)
    colors = [PRIMARY_COLOR] * len(shown)
    colors[-1] = ACCENT_COLOR
    fig.add_trace(go.Bar(
        x=shown.values, y=[str(v) for v in shown.index], orientation="h",
        marker_color=colors, text=[_fmt(v) for v in shown.values],
        textposition="outside", textfont=dict(color=MUTED, size=12),
        hovertemplate="%{y}: <b>%{x:,.0f}</b><extra></extra>",
    ))
    fig.update_xaxes(showgrid=True)
    fig.update_yaxes(showgrid=False)

    note = ""
    if len(totals) > MAX_BARS:
        note = t("ins_bar_note", lang).format(shown=MAX_BARS, total=len(totals))
    share = totals.iloc[0] / totals.sum() * 100 if totals.sum() else 0
    insight = t("ins_bar", lang).format(
        top=totals.index[0], value=_fmt(totals.iloc[0]), share=share,
        col=val_col, n=len(totals), cat=cat_col, note=note,
    )
    return _result(title, fig, insight, t("guide_bar", lang), priority=6)


def _share_donut(df, cat_col, val_col, lang="en") -> AnalysisResult | None:
    """Colorful donut showing each category's share of the total value —
    the 'Sales by Channel' style split the client asks for."""
    totals = df.groupby(cat_col)[val_col].sum()
    totals = totals[totals > 0].sort_values(ascending=False)
    if len(totals) < 2:
        return None
    if len(totals) > 6:
        head = totals.head(5)
        totals = pd.concat([head, pd.Series({t("other", lang): totals.iloc[5:].sum()})])

    title = t("title_share", lang).format(col=val_col, cat=cat_col)
    fig = _base_figure(title)
    colors = CATEGORICAL_PALETTE[:len(totals)]
    fig.add_trace(go.Pie(
        labels=[str(i) for i in totals.index], values=totals.values, hole=0.55,
        sort=False, direction="clockwise",
        marker=dict(colors=colors, line=dict(color="white", width=2)),
        textinfo="percent", textposition="inside", insidetextorientation="horizontal",
        textfont=dict(color="white", size=13),
        hovertemplate="%{label}: <b>%{value:,.0f}</b> (%{percent})<extra></extra>",
    ))
    fig.update_layout(
        showlegend=True,
        legend=dict(orientation="h", y=-0.08, x=0.5, xanchor="center",
                    font=dict(color=MUTED, size=12)),
        margin=dict(l=40, r=40, t=70, b=70),
    )

    total_sum = totals.sum()
    insight = t("ins_share", lang).format(
        top=totals.index[0], col=val_col, share=totals.iloc[0] / total_sum * 100,
        second=totals.index[1], second_share=totals.iloc[1] / total_sum * 100,
    )
    return _result(title, fig, insight, t("guide_share", lang).format(cat=cat_col, col=val_col),
                   priority=4)


def _pick_combo_pair(df, categorical) -> tuple[str, str] | None:
    """Choose two categoricals for a grouped/stacked combo: the one with the
    fewest groups (2-4) becomes the colored series, another (2-8) the x-axis."""
    counts = {c: df[c].nunique(dropna=True) for c in categorical}
    series_opts = [c for c, n in counts.items() if 2 <= n <= 4]
    if not series_opts:
        return None
    cat_b = min(series_opts, key=lambda c: counts[c])
    axis_opts = [c for c, n in counts.items() if c != cat_b and 2 <= n <= 8]
    if not axis_opts:
        return None
    cat_a = max(axis_opts, key=lambda c: counts[c])
    return cat_a, cat_b


def _combo_two_cats(df, cat_a, cat_b, val_col, lang="en") -> AnalysisResult | None:
    """Grouped (or stacked, for a 2-group series) colored bars: value by
    cat_a, split by cat_b — the campaign x channel 'combo' view."""
    pivot = (
        df.groupby([cat_a, cat_b])[val_col].sum()
        .unstack(cat_b).fillna(0)
    )
    pivot = pivot.loc[pivot.sum(axis=1).sort_values(ascending=False).head(8).index]
    pivot = pivot[pivot.sum(axis=0).sort_values(ascending=False).head(4).index]
    if pivot.shape[0] < 2 or pivot.shape[1] < 2:
        return None

    stacked = pivot.shape[1] == 2
    title = t("title_combo_stacked" if stacked else "title_combo", lang).format(
        col=val_col, cat_a=cat_a, cat_b=cat_b)
    fig = _base_figure(title)
    labels = pivot.shape[0] * pivot.shape[1] <= 12
    for idx, series in enumerate(pivot.columns):
        values = pivot[series].values
        fig.add_trace(go.Bar(
            x=[str(r) for r in pivot.index], y=values, name=str(series),
            marker=dict(color=CATEGORICAL_PALETTE[idx], line=dict(color="white", width=1.5)),
            text=[_fmt(v) for v in values] if labels else None,
            textposition="inside" if stacked else "outside",
            textfont=dict(color="white" if stacked else MUTED, size=11),
            cliponaxis=False,
            hovertemplate=f"{series} · %{{x}}: <b>%{{y:,.0f}}</b><extra></extra>",
        ))
    fig.update_layout(
        barmode="stack" if stacked else "group",
        showlegend=True,
        legend=dict(orientation="h", y=1.08, x=0, font=dict(color=MUTED)),
        margin=dict(l=70, r=40, t=90, b=60),
    )
    fig.update_xaxes(showgrid=False)

    matrix = pivot.values
    best_i, best_j = np.unravel_index(np.argmax(matrix), matrix.shape)
    col_totals = pivot.sum(axis=0)
    insight = t("ins_combo", lang).format(
        best_a=str(pivot.index[best_i]), best_b=str(pivot.columns[best_j]),
        value=_fmt(matrix[best_i, best_j]), cat_b=cat_b,
        lead=str(col_totals.idxmax()), lead_val=_fmt(col_totals.max()),
    )
    guide = t("guide_combo_stacked" if stacked else "guide_combo", lang).format(
        cat_a=cat_a, cat_b=cat_b, col=val_col)
    return _result(title, fig, insight, guide, priority=3)


def _distribution(df, val_col, lang="en") -> AnalysisResult:
    values = df[val_col].dropna()
    title = t("title_distribution", lang).format(col=val_col)
    fig = _base_figure(title)
    fig.add_trace(go.Histogram(
        x=values, nbinsx=min(30, max(10, int(np.sqrt(len(values))))),
        marker=dict(color=PRIMARY_COLOR, line=dict(color="white", width=1)),
        hovertemplate="%{x}: <b>%{y}</b><extra></extra>",
    ))
    fig.add_vline(
        x=float(values.median()), line_color=ACCENT_COLOR, line_width=2,
        annotation_text=f"{t('median', lang)} {_fmt(values.median())}",
        annotation_font=dict(color=MUTED, size=12),
    )
    insight = t("ins_distribution", lang).format(
        col=val_col, vmin=_fmt(values.min()), vmax=_fmt(values.max()),
        median=_fmt(values.median()), mean=_fmt(values.mean()), n=len(values),
    )
    return _result(title, fig, insight, t("guide_distribution", lang), priority=7)


def _correlation(df, numeric, lang="en") -> AnalysisResult | None:
    cols = numeric[:8]
    corr = df[cols].corr()
    if corr.isna().all().all():
        return None
    title = t("title_correlation", lang)
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
    insight = t("ins_correlation", lang).format(
        a=col_a, b=col_b, value=strongest,
        word=t("positively" if strongest > 0 else "negatively", lang),
    )
    return _result(title, fig, insight, t("guide_correlation", lang), priority=8)


def auto_visualize(df: pd.DataFrame, max_charts: int = 10,
                   lang: str = "en") -> list[AnalysisResult]:
    """Build a dashboard-style chart set + computed insights, LLM-free."""
    numeric, categorical, datetime_cols = _profile(df)
    val_col = _pick_value_column(numeric)
    results: list[AnalysisResult] = []

    if val_col and datetime_cols:
        for builder in (_trend_over_time, _growth_by_period, _weekday_pattern):
            chart = builder(df, datetime_cols[0], val_col, lang=lang)
            if chart:
                results.append(chart)
        if categorical:
            for builder in (_trend_by_category, _month_category_heatmap):
                chart = builder(df, datetime_cols[0], val_col, categorical[0], lang=lang)
                if chart:
                    results.append(chart)
    if val_col and categorical:
        donut_col = next(
            (c for c in categorical if 3 <= df[c].nunique(dropna=True) <= 8),
            categorical[0],
        )
        share = _share_donut(df, donut_col, val_col, lang=lang)
        if share:
            results.append(share)
        pair = _pick_combo_pair(df, categorical)
        if pair:
            combo = _combo_two_cats(df, pair[0], pair[1], val_col, lang=lang)
            if combo:
                results.append(combo)
    if val_col:
        for cat_col in categorical[:3]:
            results.append(_bar_by_category(df, cat_col, val_col, lang=lang))
        results.append(_distribution(df, val_col, lang=lang))
    if len(numeric) >= 3:
        heatmap = _correlation(df, numeric, lang=lang)
        if heatmap:
            results.append(heatmap)
    results.sort(key=lambda r: r.priority)

    if not results:
        return [AnalysisResult(
            question="Auto-visualization", kind="error",
            text=t("no_chartable", lang),
        )]
    return results[:max_charts]
