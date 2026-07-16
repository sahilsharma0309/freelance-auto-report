"""3D & animated visualizations — interactive-only studio.

These are for exploring in the app (drag/swipe to rotate, press play to
animate); the printable report keeps the standard 2D charts, which stay
readable on paper. Colors reuse the validated brand palette.
"""

import pandas as pd
import plotly.graph_objects as go

from core.analysis import AnalysisResult
from core.autoviz import (
    FONT_STACK,
    INK,
    MUTED,
    _fmt,
    _pick_value_column,
    _profile,
)
from core.branding import ACCENT_COLOR, PRIMARY_COLOR, SERIES_PALETTE
from core.i18n import t

MAX_POINTS = 2_000
RACE_TOP_N = 6

_SCENE_AXIS = dict(
    gridcolor="#e8eaed", backgroundcolor="white",
    tickfont=dict(color=MUTED, size=10),
)


def _layout(fig: go.Figure, title: str) -> go.Figure:
    fig.update_layout(
        title=dict(text=f"<b>{title}</b>", x=0.01, font=dict(size=17, color=INK)),
        font=dict(family=FONT_STACK, color=INK, size=13),
        paper_bgcolor="white",
        margin=dict(l=10, r=10, t=60, b=10),
        hoverlabel=dict(bgcolor=PRIMARY_COLOR, font=dict(color="white", size=12)),
        height=560,
    )
    return fig


def _scatter_3d(df, numeric, categorical, lang) -> AnalysisResult | None:
    if len(numeric) < 3:
        return None
    x_col, y_col, z_col = numeric[:3]
    sample = df[[x_col, y_col, z_col] + categorical[:1]].dropna()
    if len(sample) > MAX_POINTS:
        sample = sample.sample(MAX_POINTS, random_state=7)

    title = t("title_3d_scatter", lang).format(x=x_col, y=y_col, z=z_col)
    fig = go.Figure()
    if categorical:
        cat_col = categorical[0]
        top = sample[cat_col].astype(str).value_counts().index[:len(SERIES_PALETTE)]
        for idx, group in enumerate(top):
            part = sample[sample[cat_col].astype(str) == group]
            fig.add_trace(go.Scatter3d(
                x=part[x_col], y=part[y_col], z=part[z_col],
                mode="markers", name=str(group),
                marker=dict(size=3.5, color=SERIES_PALETTE[idx], opacity=0.75),
                hovertemplate=(f"{group}<br>{x_col}: %{{x:,.0f}}<br>"
                               f"{y_col}: %{{y:,.0f}}<br>{z_col}: %{{z:,.0f}}"
                               "<extra></extra>"),
            ))
        fig.update_layout(showlegend=True,
                          legend=dict(orientation="h", y=1.02, x=0))
    else:
        fig.add_trace(go.Scatter3d(
            x=sample[x_col], y=sample[y_col], z=sample[z_col],
            mode="markers",
            marker=dict(size=3.5, color=PRIMARY_COLOR, opacity=0.75),
            hovertemplate=(f"{x_col}: %{{x:,.0f}}<br>{y_col}: %{{y:,.0f}}<br>"
                           f"{z_col}: %{{z:,.0f}}<extra></extra>"),
        ))
    _layout(fig, title)
    fig.update_layout(scene=dict(
        xaxis=dict(title=x_col, **_SCENE_AXIS),
        yaxis=dict(title=y_col, **_SCENE_AXIS),
        zaxis=dict(title=z_col, **_SCENE_AXIS),
    ))
    return AnalysisResult(question=title, kind="chart", figure=fig,
                          guide=t("guide_3d_scatter", lang), priority=11)


def _month_cat_pivot(df, date_col, val_col, cat_col) -> pd.DataFrame | None:
    dates = pd.to_datetime(df[date_col], errors="coerce", format="mixed")
    frame = pd.DataFrame({
        "d": dates, "v": df[val_col], "c": df[cat_col].astype(str),
    }).dropna()
    if frame.empty or (frame["d"].max() - frame["d"].min()).days <= 92:
        return None
    top = frame.groupby("c")["v"].sum().nlargest(8).index
    frame = frame[frame["c"].isin(top)]
    frame["month"] = frame["d"].dt.to_period("M").dt.to_timestamp()
    pivot = frame.pivot_table(index="c", columns="month", values="v",
                              aggfunc="sum").fillna(0)
    return pivot if pivot.shape[1] >= 3 else None


def _surface_3d(df, date_col, val_col, cat_col, lang) -> AnalysisResult | None:
    pivot = _month_cat_pivot(df, date_col, val_col, cat_col)
    if pivot is None:
        return None
    title = t("title_3d_surface", lang).format(col=val_col, cat=cat_col)
    fig = go.Figure(go.Surface(
        z=pivot.values,
        x=[f"{m:%b %y}" for m in pivot.columns],
        y=list(pivot.index),
        colorscale=[[0.0, "#f6f7f9"], [0.55, "#7C8DB0"], [1.0, PRIMARY_COLOR]],
        colorbar=dict(tickfont=dict(color=MUTED)),
        hovertemplate="%{y} · %{x}: <b>%{z:,.0f}</b><extra></extra>",
    ))
    _layout(fig, title)
    fig.update_layout(scene=dict(
        xaxis=dict(title="", **_SCENE_AXIS),
        yaxis=dict(title="", **_SCENE_AXIS),
        zaxis=dict(title=val_col, **_SCENE_AXIS),
        camera=dict(eye=dict(x=1.6, y=-1.6, z=0.9)),
    ))
    return AnalysisResult(question=title, kind="chart", figure=fig,
                          guide=t("guide_3d_surface", lang), priority=12)


def _animated_race(df, date_col, val_col, cat_col, lang) -> AnalysisResult | None:
    pivot = _month_cat_pivot(df, date_col, val_col, cat_col)
    if pivot is None:
        return None
    cumulative = pivot.T.sort_index().cumsum()  # months x categories, running total
    order = cumulative.iloc[-1].sort_values().index.tolist()[-RACE_TOP_N:]
    cumulative = cumulative[order]
    months = list(cumulative.index)
    colors = [SERIES_PALETTE[i % len(SERIES_PALETTE)] for i in range(len(order))]

    def bars(month) -> go.Bar:
        row = cumulative.loc[month]
        return go.Bar(
            x=row.values, y=[str(c) for c in order], orientation="h",
            marker_color=colors, text=[_fmt(v) for v in row.values],
            textposition="outside", textfont=dict(color=MUTED, size=11),
            hovertemplate="%{y}: <b>%{x:,.0f}</b><extra></extra>",
        )

    title = t("title_race", lang).format(col=val_col, cat=cat_col)
    x_max = float(cumulative.values.max()) * 1.15
    fig = go.Figure(
        data=[bars(months[0])],
        frames=[go.Frame(data=[bars(m)], name=f"{m:%b %Y}") for m in months],
    )
    _layout(fig, title)
    fig.update_layout(
        xaxis=dict(range=[0, x_max], gridcolor="#e8eaed",
                   tickfont=dict(color=MUTED, size=11)),
        yaxis=dict(tickfont=dict(color=MUTED, size=12)),
        barcornerradius=5,
        updatemenus=[dict(
            type="buttons", x=0, y=1.15, xanchor="left",
            buttons=[
                dict(label="▶ Play", method="animate",
                     args=[None, dict(frame=dict(duration=450, redraw=True),
                                      fromcurrent=True,
                                      transition=dict(duration=250))]),
                dict(label="⏸", method="animate",
                     args=[[None], dict(frame=dict(duration=0), mode="immediate")]),
            ],
        )],
        sliders=[dict(
            steps=[dict(label=f"{m:%b %y}", method="animate",
                        args=[[f"{m:%b %Y}"],
                              dict(frame=dict(duration=0, redraw=True),
                                   mode="immediate")])
                   for m in months],
            currentvalue=dict(prefix="", font=dict(color=MUTED, size=12)),
        )],
    )
    return AnalysisResult(question=title, kind="chart", figure=fig,
                          guide=t("guide_race", lang), priority=13)


def studio_3d(df: pd.DataFrame, lang: str = "en") -> tuple[list[AnalysisResult], list[str]]:
    """Build the 3D/animated set. Returns (results, notes-about-missing-data)."""
    numeric, categorical, datetime_cols = _profile(df)
    val_col = _pick_value_column(numeric)
    results: list[AnalysisResult] = []
    notes: list[str] = []

    scatter = _scatter_3d(df, numeric, categorical, lang)
    if scatter:
        results.append(scatter)
    else:
        notes.append(t("need_3_numeric", lang))

    if val_col and datetime_cols and categorical:
        for builder in (_surface_3d, _animated_race):
            chart = builder(df, datetime_cols[0], val_col, categorical[0], lang)
            if chart:
                results.append(chart)
        if len(results) == (1 if scatter else 0):
            notes.append(t("need_time_cat", lang))
    else:
        notes.append(t("need_time_cat", lang))

    return results, notes
