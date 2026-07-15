"""Branded PDF export via WeasyPrint.

Builds a self-contained HTML document (charts and logo embedded as data
URIs) and renders it to PDF bytes. The same AnalysisResult objects the
Streamlit UI displays are the input, so what you see is what you export.
"""

import base64
import html
from datetime import date

import pandas as pd
from weasyprint import HTML

from core.analysis import AnalysisResult
from core.branding import (
    ACCENT_COLOR,
    BRAND_NAME,
    LOGO_PATH,
    MONOGRAM,
    PAGE_WATERMARK_TEXT,
    PRIMARY_COLOR,
    WATERMARK_TEXT,
)

# Very light diagonal name across every page, drawn as the page background
_WATERMARK_SVG = (
    "data:image/svg+xml;utf8,"
    "<svg xmlns='http://www.w3.org/2000/svg' width='700' height='700'>"
    "<text x='350' y='350' font-size='58' font-family='Helvetica,Arial'"
    f" fill='{PRIMARY_COLOR.replace('#', '%23')}' fill-opacity='0.05'"
    " text-anchor='middle' transform='rotate(-35 350 350)'>"
    f"{PAGE_WATERMARK_TEXT}</text></svg>"
)

MAX_TABLE_ROWS = 20

_CSS = """
@page {
    size: A4;
    margin: 2cm 1.8cm 2.4cm 1.8cm;
    background: url("%(watermark_svg)s") no-repeat center center;
    @bottom-center {
        content: "%(watermark)s";
        color: %(accent)s;
        font-size: 9pt;
        font-style: italic;
        font-family: Georgia, serif;
    }
    @bottom-right {
        content: "Page " counter(page) " of " counter(pages);
        color: #8a8f98;
        font-size: 8pt;
    }
}
body { font-family: Helvetica, Arial, sans-serif; color: #23272e; font-size: 10.5pt; }
.header { border-bottom: 3px solid %(accent)s; padding-bottom: 12px; margin-bottom: 6px;
          display: flex; align-items: center; }
.logo { height: 52px; margin-right: 14px; }
.monogram { display: inline-block; width: 52px; height: 52px; line-height: 52px;
            border-radius: 50%%; background: %(primary)s; color: %(accent)s;
            font-weight: bold; font-size: 18pt; text-align: center; margin-right: 14px; }
.brand { color: %(primary)s; font-size: 16pt; font-weight: bold; }
.meta { color: #6a707a; font-size: 9pt; margin-bottom: 16px; }
.kpis { display: flex; gap: 10px; margin: 0 0 24px 0; }
.kpi { flex: 1; border: 1px solid #e3e5e8; border-top: 3px solid %(accent)s;
       padding: 8px 12px; }
.kpi-label { font-size: 7.5pt; color: #6a707a; text-transform: uppercase;
             letter-spacing: 0.06em; }
.kpi-value { font-size: 15pt; color: %(primary)s; font-weight: bold; }
.kpi-delta { font-size: 7.5pt; color: %(accent)s; }
h1 { color: %(primary)s; font-size: 15pt; margin: 18px 0 4px 0; }
.section { margin-bottom: 22px; page-break-inside: avoid; }
.question { color: %(primary)s; font-size: 12pt; font-weight: bold;
            border-left: 4px solid %(accent)s; padding-left: 8px; margin-bottom: 8px; }
.chart { max-width: 100%%; margin: 6px 0; }
.insight { background: #f6f4ee; border-left: 3px solid %(accent)s;
           padding: 8px 12px; font-size: 10pt; }
table { border-collapse: collapse; width: 100%%; font-size: 9pt; margin: 6px 0; }
th { background: %(primary)s; color: white; padding: 5px 8px; text-align: left; }
td { border-bottom: 1px solid #e3e5e8; padding: 4px 8px; }
tr:nth-child(even) td { background: #f4f6f9; }
.truncated { color: #8a8f98; font-size: 8pt; font-style: italic; }
.error { color: #a33; }
""" % {
    "primary": PRIMARY_COLOR,
    "accent": ACCENT_COLOR,
    "watermark": WATERMARK_TEXT,
    "watermark_svg": _WATERMARK_SVG,
}


def _logo_html() -> str:
    if LOGO_PATH.exists():
        encoded = base64.b64encode(LOGO_PATH.read_bytes()).decode()
        return f'<img class="logo" src="data:image/png;base64,{encoded}" alt="logo"/>'
    return f'<span class="monogram">{html.escape(MONOGRAM)}</span>'


def _chart_html(path: str) -> str:
    with open(path, "rb") as fh:
        encoded = base64.b64encode(fh.read()).decode()
    return f'<img class="chart" src="data:image/png;base64,{encoded}"/>'


def _table_html(df: pd.DataFrame) -> str:
    shown = df.head(MAX_TABLE_ROWS)
    table = shown.to_html(index=False, border=0, escape=True)
    note = ""
    if len(df) > MAX_TABLE_ROWS:
        note = f'<p class="truncated">Showing first {MAX_TABLE_ROWS} of {len(df)} rows.</p>'
    return table + note


def _section_html(result: AnalysisResult) -> str:
    parts = [f'<div class="section"><p class="question">{html.escape(result.question)}</p>']
    if result.kind == "chart":
        if result.chart_path:
            parts.append(_chart_html(result.chart_path))
        if result.text:
            parts.append(f'<p class="insight">{html.escape(result.text)}</p>')
    elif result.kind == "dataframe" and result.dataframe is not None:
        parts.append(_table_html(result.dataframe))
    elif result.kind == "error":
        parts.append(f'<p class="error">{html.escape(result.text)}</p>')
    else:
        parts.append(f'<p class="insight">{html.escape(result.text)}</p>')
    parts.append("</div>")
    return "".join(parts)


def _kpis_html(kpis) -> str:
    if not kpis:
        return ""
    tiles = "".join(
        f'<div class="kpi"><div class="kpi-label">{html.escape(k.label)}</div>'
        f'<div class="kpi-value">{html.escape(k.value)}</div>'
        f'<div class="kpi-delta">{html.escape(k.delta)}</div></div>'
        for k in kpis
    )
    return f'<div class="kpis">{tiles}</div>'


def build_html(results: list[AnalysisResult], title: str, dataset_name: str,
               kpis=None, client_name: str = "") -> str:
    sections = "".join(_section_html(r) for r in results)
    client = (
        f" &nbsp;·&nbsp; Prepared for {html.escape(client_name)}" if client_name else ""
    )
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>{_CSS}</style></head>
<body>
  <div class="header">{_logo_html()}<span class="brand">{html.escape(BRAND_NAME)}</span></div>
  <h1>{html.escape(title)}</h1>
  <p class="meta">Dataset: {html.escape(dataset_name)} &nbsp;·&nbsp; {date.today():%d %B %Y}{client}</p>
  {_kpis_html(kpis)}
  {sections}
</body></html>"""


def export_pdf(results: list[AnalysisResult], title: str, dataset_name: str,
               kpis=None, client_name: str = "") -> bytes:
    return HTML(
        string=build_html(results, title, dataset_name, kpis, client_name)
    ).write_pdf()
