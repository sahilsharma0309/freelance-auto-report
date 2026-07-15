"""Google-Analytics-style KPI cards computed straight from the dataframe."""

from dataclasses import dataclass

import pandas as pd

from core.autoviz import _fmt, _pick_value_column, _profile


@dataclass
class Kpi:
    label: str
    value: str
    delta: str = ""  # e.g. "+12.4% vs previous period"


def compute_kpis(df: pd.DataFrame) -> list[Kpi]:
    numeric, categorical, datetime_cols = _profile(df)
    val_col = _pick_value_column(numeric)
    kpis: list[Kpi] = [Kpi("Records", f"{len(df):,}")]

    if val_col:
        values = df[val_col].dropna()
        kpis.append(Kpi(f"Total {val_col}", _fmt(values.sum())))
        kpis.append(Kpi(f"Avg {val_col}", _fmt(values.mean())))

    if val_col and datetime_cols:
        dates = pd.to_datetime(df[datetime_cols[0]], errors="coerce", format="mixed")
        monthly = (
            pd.DataFrame({"d": dates, "v": df[val_col]})
            .dropna()
            .set_index("d")["v"]
            .resample("MS")
            .sum()
        )
        monthly = monthly[monthly != 0]
        if len(monthly) >= 2:
            last, prev = monthly.iloc[-1], monthly.iloc[-2]
            if prev:
                change = (last - prev) / abs(prev) * 100
                kpis.append(Kpi(
                    f"{monthly.index[-1]:%b %Y} {val_col}",
                    _fmt(last),
                    f"{change:+.1f}% vs {monthly.index[-2]:%b}",
                ))
    elif categorical:
        top_col = categorical[0]
        kpis.append(Kpi(f"Distinct {top_col}", f"{df[top_col].nunique():,}"))

    return kpis[:4]
