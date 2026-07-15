"""Freelance Auto-Report — upload data, get a client-ready branded report.

Run with:  streamlit run app.py
"""

from datetime import date

import pandas as pd
import streamlit as st

from core.analysis import (
    AnalysisResult,
    ask,
    configure_llm,
    load_dataframe,
    story_order,
    to_chat_frame,
)
from core.autoviz import _profile, auto_visualize
from core.kpis import compute_kpis
from core.report_docx import export_docx
from core.settings import GROQ_API_KEY, LLM_MODEL, UPLOADS_DIR

# WeasyPrint needs system libraries (GTK3 on Windows, pango/cairo on Linux).
# If they're missing, keep the app usable and only disable PDF export.
try:
    from core.report_pdf import export_pdf
except OSError:
    export_pdf = None

st.set_page_config(page_title="Freelance Auto-Report", page_icon="📊", layout="wide")

st.title("📊 Freelance Auto-Report")
st.caption(
    "Upload a CSV/Excel file → get an instant dashboard → export a branded, "
    "signed PDF/Word report."
)

# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.header("Settings")
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
uploaded = st.file_uploader("Upload your data file", type=["csv", "xlsx", "xls"])

df = None
dataset_name = uploaded.name if uploaded is not None else "dataset"
if uploaded is not None:
    saved_path = UPLOADS_DIR / uploaded.name
    saved_path.write_bytes(uploaded.getbuffer())
    try:
        df = load_dataframe(saved_path)
    except Exception as exc:
        st.error(f"Could not read file: {exc}")
    else:
        st.success(f"Loaded **{uploaded.name}** — {len(df)} rows × {len(df.columns)} columns")
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
            selected = st.multiselect(col, options, default=options)
            if len(selected) != len(options):
                fdf = fdf[fdf[col].astype(str).isin(selected)]
        if len(fdf) != len(df):
            st.caption(f"{len(fdf):,} of {len(df):,} rows after filters")

    kpis = compute_kpis(fdf)
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
                    ] + auto_visualize(fdf.head(100_000))
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
                    result = ask(to_chat_frame(fdf), question.strip())
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
            results = story_order(st.session_state.history)
            stem = f"{report_title.strip().replace(' ', '_') or 'report'}_{date.today():%Y-%m-%d}"

            col_pdf, col_docx = st.columns(2)
            with col_pdf:
                if export_pdf is None:
                    st.warning(
                        "PDF export needs the GTK3 runtime on Windows. Install it from "
                        "[gtk3-runtime releases](https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases) "
                        "and restart the app. Word export works without it."
                    )
                else:
                    try:
                        pdf_bytes = export_pdf(results, report_title, dataset_name,
                                               kpis=compute_kpis(fdf) if fdf is not None else None,
                                               client_name=client_name.strip())
                        st.download_button(
                            "⬇️ Download PDF", pdf_bytes, file_name=f"{stem}.pdf",
                            mime="application/pdf", use_container_width=True,
                        )
                    except Exception as exc:
                        st.error(f"PDF export failed: {exc}")
            with col_docx:
                try:
                    docx_bytes = export_docx(results, report_title, dataset_name,
                                             kpis=compute_kpis(fdf) if fdf is not None else None,
                                             client_name=client_name.strip())
                    st.download_button(
                        "⬇️ Download Word", docx_bytes, file_name=f"{stem}.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        use_container_width=True,
                    )
                except Exception as exc:
                    st.error(f"Word export failed: {exc}")
