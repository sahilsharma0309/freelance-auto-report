"""Freelance Auto-Report — ask your data questions in plain English.

Run with:  streamlit run app.py
"""

from datetime import date

import streamlit as st

from core.analysis import AnalysisResult, ask, configure_llm, load_dataframe
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
st.caption("Upload a CSV/Excel file, ask a question in plain English, get a chart + insight.")

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
    st.session_state.history = []  # list[AnalysisResult], newest last
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

# ---------------------------------------------------------------- ask
if df is not None:
    question = st.text_input(
        "Ask a question about your data",
        placeholder="e.g. Plot monthly revenue by region as a bar chart",
    )
    col_ask, col_auto = st.columns(2)
    with col_ask:
        if st.button("Analyze", type="primary", disabled=not question.strip(),
                     use_container_width=True):
            if not GROQ_API_KEY:
                st.error("Set GROQ_API_KEY in .env first.")
            else:
                if not st.session_state.llm_ready:
                    configure_llm()
                    st.session_state.llm_ready = True
                with st.spinner("Thinking..."):
                    result = ask(df, question.strip())
                st.session_state.history.append(result)
    with col_auto:
        if st.button("📊 Auto-Visualize (no AI)", use_container_width=True,
                     help="Instant branded charts + computed insights straight "
                          "from the data — no LLM, no rate limits."):
            from core.autoviz import auto_visualize
            with st.spinner("Building charts..."):
                st.session_state.history.extend(auto_visualize(df.head(100_000)))

# ---------------------------------------------------------------- results
def render(result: AnalysisResult) -> None:
    st.markdown(f"**Q: {result.question}**")
    if result.kind == "chart":
        if result.chart_path:
            st.image(result.chart_path)
        if result.text:
            st.markdown(f"💡 {result.text}")
    elif result.kind == "dataframe":
        st.dataframe(result.dataframe, use_container_width=True)
    elif result.kind == "error":
        st.error(result.text)
    else:
        st.markdown(result.text)


if st.session_state.history:
    st.divider()
    st.subheader("Results")
    for item in reversed(st.session_state.history):
        render(item)
        st.divider()

    # ------------------------------------------------------------ export
    st.subheader("Export Report")
    report_title = st.text_input("Report title", value="Data Analysis Report")
    results = list(reversed(st.session_state.history))  # newest first, same as on screen
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
                pdf_bytes = export_pdf(results, report_title, dataset_name)
                st.download_button(
                    "⬇️ Download PDF", pdf_bytes, file_name=f"{stem}.pdf",
                    mime="application/pdf", use_container_width=True,
                )
            except Exception as exc:
                st.error(f"PDF export failed: {exc}")
    with col_docx:
        try:
            docx_bytes = export_docx(results, report_title, dataset_name)
            st.download_button(
                "⬇️ Download Word", docx_bytes, file_name=f"{stem}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True,
            )
        except Exception as exc:
            st.error(f"Word export failed: {exc}")
