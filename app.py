"""Freelance Auto-Report — upload data, get a client-ready branded report.

Run with:  streamlit run app.py
"""

import re
from datetime import date

import pandas as pd
import streamlit as st

from core.analysis import (
    AnalysisResult,
    ask,
    configure_llm,
    story_order,
    to_chat_frame,
)
from core.autoviz import _profile, auto_visualize
from core.branding import ACCENT_COLOR, BRAND_NAME, MONOGRAM, PRIMARY_COLOR
from core.i18n import LANGUAGES
from core.kpis import compute_kpis
from core.report_docx import export_docx
from core.settings import GROQ_API_KEY, LLM_MODEL, UPLOADS_DIR

MAX_FILES = 5
COMBINE_LABEL = "🔗 All files combined"

# WeasyPrint needs system libraries (GTK3 on Windows, pango/cairo on Linux).
# If they're missing, keep the app usable and only disable PDF export.
try:
    from core.report_pdf import export_pdf
except OSError:
    export_pdf = None

st.set_page_config(page_title=BRAND_NAME, page_icon="📊", layout="wide")

# ------------------------------------------------- SaaS look & feel
st.markdown(
    f"""<style>
    #MainMenu, footer {{visibility: hidden;}}
    div[data-testid="stMetric"] {{
        background: #ffffff; border: 1px solid #e3e5e8;
        border-top: 3px solid {ACCENT_COLOR};
        padding: 14px 18px; border-radius: 8px;
        box-shadow: 0 1px 3px rgba(26,43,76,0.06);
    }}
    div[data-testid="stMetric"] label {{ color: #6a707a; }}
    .stTabs [data-baseweb="tab"] {{ font-weight: 600; }}
    div[data-testid="stFileUploader"] section {{ border-radius: 8px; }}
    </style>""",
    unsafe_allow_html=True,
)
st.markdown(
    f"""<div style="display:flex;align-items:center;gap:14px;padding:6px 0 14px 0;
         border-bottom:3px solid {ACCENT_COLOR};margin-bottom:16px">
      <div style="width:46px;height:46px;border-radius:50%;background:{PRIMARY_COLOR};
           color:{ACCENT_COLOR};display:flex;align-items:center;justify-content:center;
           font-weight:700;font-size:20px">{MONOGRAM}</div>
      <div>
        <div style="font-size:25px;font-weight:700;color:{PRIMARY_COLOR};line-height:1.15">
          {BRAND_NAME}</div>
        <div style="color:#6a707a;font-size:14px">
          Upload data → instant dashboard → branded client report</div>
      </div>
    </div>""",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.header("Settings")
    lang_label = st.radio(
        "Report language / रिपोर्ट की भाषा",
        list(LANGUAGES), horizontal=True,
        help="Charts, insights, reading guides, and the exported report "
             "are written in this language.",
    )
    lang = LANGUAGES[lang_label]
    if GROQ_API_KEY:
        st.success("Groq API key loaded from .env")
    else:
        st.error("No GROQ_API_KEY found — copy .env.example to .env and add your key.")
    st.text(f"Model: {LLM_MODEL}")
    st.divider()
    if st.button("Clear analysis history"):
        st.session_state.history = []
        st.rerun()

if "history" not in st.session_state:
    st.session_state.history = []  # list[AnalysisResult]
if "llm_ready" not in st.session_state:
    st.session_state.llm_ready = False

# ---------------------------------------------------------------- upload
uploads = st.file_uploader(
    f"Upload your data files (up to {MAX_FILES} — CSV or Excel)",
    type=["csv", "xlsx", "xls"], accept_multiple_files=True,
)
if uploads and len(uploads) > MAX_FILES:
    st.warning(f"Using the first {MAX_FILES} files only.")
    uploads = uploads[:MAX_FILES]


def _read_upload(uploaded) -> pd.DataFrame | None:
    saved_path = UPLOADS_DIR / uploaded.name
    saved_path.write_bytes(uploaded.getbuffer())
    try:
        if saved_path.suffix.lower() == ".csv":
            return pd.read_csv(saved_path)
        return pd.read_excel(saved_path)
    except Exception as exc:
        st.error(f"Could not read {uploaded.name}: {exc}")
        return None


df = None
dataset_name = "dataset"
if uploads:
    frames = {u.name: frame for u in uploads
              if (frame := _read_upload(u)) is not None}
    if frames:
        options = list(frames)
        same_columns = len(frames) > 1 and len(
            {tuple(sorted(f.columns)) for f in frames.values()}
        ) == 1
        if same_columns:
            options = [COMBINE_LABEL] + options
        choice = options[0] if len(options) == 1 else st.selectbox(
            "Which dataset do you want to analyze?", options,
        )
        if choice == COMBINE_LABEL:
            df = pd.concat(frames.values(), ignore_index=True)
            dataset_name = f"{len(frames)} files combined"
        else:
            df = frames[choice]
            dataset_name = choice
        st.success(f"Loaded **{dataset_name}** — {len(df):,} rows × {len(df.columns)} columns")
        if len(frames) > 1 and not same_columns:
            st.caption("Files have different columns, so they can't be combined — "
                       "pick one at a time from the dropdown.")
        with st.expander("Preview data", expanded=False):
            st.dataframe(df.head(50), use_container_width=True)

# ------------------------------------------------------- filters + KPIs
fdf = None
if df is not None:
    fdf = pd.DataFrame(df).copy()
    _, cat_cols, date_cols = _profile(fdf)

    with st.sidebar:
        st.header("Filters")
        for col in date_cols[:1]:
            dates = pd.to_datetime(fdf[col], errors="coerce", format="mixed")
            d_min, d_max = dates.min().date(), dates.max().date()
            picked = st.date_input(col, (d_min, d_max),
                                   min_value=d_min, max_value=d_max)
            if isinstance(picked, tuple) and len(picked) == 2:
                mask = (dates.dt.date >= picked[0]) & (dates.dt.date <= picked[1])
                fdf = fdf[mask]
        for col in cat_cols[:2]:
            options = sorted(str(v) for v in fdf[col].dropna().unique())
            selected = st.multiselect(
                col, options, default=[],
                placeholder=f"All {col} (pick to filter)",
            )
            if selected:
                fdf = fdf[fdf[col].astype(str).isin(selected)]
        if len(fdf) != len(df):
            st.caption(f"{len(fdf):,} of {len(df):,} rows after filters")

    kpis = compute_kpis(fdf, lang)
    kpi_cols = st.columns(max(len(kpis), 1))
    for slot, kpi in zip(kpi_cols, kpis):
        slot.metric(kpi.label, kpi.value, kpi.delta or None)


# ---------------------------------------------------------------- render
def render(result: AnalysisResult) -> None:
    st.markdown(f"**{result.question}**")
    if result.kind == "chart":
        if result.figure is not None:
            st.plotly_chart(result.figure, use_container_width=True)
        elif result.chart_path:
            st.image(result.chart_path)
        if result.text:
            st.markdown(f"💡 {result.text}")
        if result.guide:
            st.caption(f"📖 How to read: {result.guide}")
    elif result.kind == "dataframe":
        st.dataframe(result.dataframe, use_container_width=True)
    elif result.kind == "error":
        st.error(result.text)
    else:
        st.markdown(result.text)
    st.divider()


# ---------------------------------------------------------------- tabs
if df is not None:
    tab_dash, tab_ask, tab_export = st.tabs(
        ["📊 Dashboard", "🤖 Ask AI", "📄 Export Report"]
    )

    with tab_dash:
        left, right = st.columns([2, 3])
        with left:
            if st.button("📊 Build dashboard (no AI)", type="primary",
                         use_container_width=True,
                         help="Instant branded charts + computed insights straight "
                              "from the data — no LLM, no rate limits. Respects the "
                              "sidebar filters."):
                with st.spinner("Building charts..."):
                    st.session_state.history = [
                        r for r in st.session_state.history if r.priority >= 9
                    ] + auto_visualize(fdf.head(100_000), lang=lang)
        with right:
            with st.expander("📖 New to charts? Read this first (simple guide)"):
                st.markdown(
                    "1. **Start with the big numbers on top** — total business, "
                    "average, and whether the latest month is up (green) or "
                    "down (red).\n"
                    "2. **Then the first chart (trend)** — line going up means "
                    "business growing, going down means slowing.\n"
                    "3. **Growth chart** — navy bars = better than last month, "
                    "gold bars = down from last month.\n"
                    "4. **Comparison & ranking charts** — whoever is higher or "
                    "longer is winning; gold marks the No. 1.\n"
                    "5. **Every chart has a 💡 line** (the finding, in words) "
                    "and a 📖 line (how to read it) — reading just these two "
                    "lines tells you the whole story.\n"
                    "6. **Hover your mouse over any chart** to see exact numbers."
                )
        story = story_order(st.session_state.history)
        dash_results = [r for r in story if r.priority < 9]
        if dash_results:
            for item in dash_results:
                render(item)
        else:
            st.info("Click **Build dashboard** to generate the full chart set from your data.")

    with tab_ask:
        question = st.text_input(
            "Ask a question about your data",
            placeholder="e.g. Plot monthly revenue by region as a bar chart",
        )
        if st.button("Analyze", type="primary", disabled=not question.strip()):
            if not GROQ_API_KEY:
                st.error("Set GROQ_API_KEY in .env first.")
            else:
                if not st.session_state.llm_ready:
                    configure_llm()
                    st.session_state.llm_ready = True
                with st.spinner("Thinking..."):
                    result = ask(to_chat_frame(fdf), question.strip(), lang=lang)
                st.session_state.history.append(result)
        qa_results = [r for r in st.session_state.history if r.priority >= 9]
        for item in reversed(qa_results):
            render(item)

    with tab_export:
        if not st.session_state.history:
            st.info("Build the dashboard (or ask a question) first — the report "
                    "collects everything you generated.")
        else:
            col_title, col_client = st.columns(2)
            with col_title:
                report_title = st.text_input("Report title", value="Data Analysis Report")
            with col_client:
                client_name = st.text_input("Prepared for (client, optional)", value="")
            st.caption(
                "The report opens with KPI tiles and Key Findings, then charts in "
                "story order (trend → growth → comparisons → rankings), each with "
                "a plain-language 'How to read' line — made for non-technical clients."
            )
            # Two-step export: an explicit Generate click reads the final
            # title/client values, so a name typed just before downloading
            # is never lost to Streamlit's stale-rerun behavior.
            if st.button("🧾 Generate report files", type="primary",
                         use_container_width=True):
                results = story_order(st.session_state.history)
                report_kpis = compute_kpis(fdf, lang) if fdf is not None else None
                parts = [report_title.strip() or "report"]
                if client_name.strip():
                    parts.append(client_name.strip())
                parts.append(f"{date.today():%Y-%m-%d}")
                stem = "_".join(
                    re.sub(r"[^A-Za-z0-9-]+", "_", p).strip("_") for p in parts
                )
                report_files = {"stem": stem}
                with st.spinner("Building your report..."):
                    if export_pdf is not None:
                        try:
                            report_files["pdf"] = export_pdf(
                                results, report_title, dataset_name,
                                kpis=report_kpis, client_name=client_name.strip(),
                                lang=lang,
                            )
                        except Exception as exc:
                            st.error(f"PDF export failed: {exc}")
                    try:
                        report_files["docx"] = export_docx(
                            results, report_title, dataset_name,
                            kpis=report_kpis, client_name=client_name.strip(),
                            lang=lang,
                        )
                    except Exception as exc:
                        st.error(f"Word export failed: {exc}")
                st.session_state.report_files = report_files

            files = st.session_state.get("report_files")
            if files:
                col_pdf, col_docx = st.columns(2)
                with col_pdf:
                    if export_pdf is None:
                        st.warning(
                            "PDF export needs the GTK3 runtime on Windows. Install it from "
                            "[gtk3-runtime releases](https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases) "
                            "and restart the app. Word export works without it."
                        )
                    elif "pdf" in files:
                        st.download_button(
                            "⬇️ Download PDF", files["pdf"],
                            file_name=f"{files['stem']}.pdf",
                            mime="application/pdf", use_container_width=True,
                        )
                with col_docx:
                    if "docx" in files:
                        st.download_button(
                            "⬇️ Download Word", files["docx"],
                            file_name=f"{files['stem']}.docx",
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            use_container_width=True,
                        )
                st.caption("Changed the title, client, language, or charts? "
                           "Click **Generate report files** again to refresh the downloads.")
