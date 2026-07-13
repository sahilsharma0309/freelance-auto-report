"""Freelance Auto-Report — ask your data questions in plain English.

Run with:  streamlit run app.py
"""

import streamlit as st

from core.analysis import AnalysisResult, ask, configure_llm, load_dataframe
from core.settings import GROQ_API_KEY, LLM_MODEL, UPLOADS_DIR

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
    if st.button("Analyze", type="primary", disabled=not question.strip()):
        if not GROQ_API_KEY:
            st.error("Set GROQ_API_KEY in .env first.")
        else:
            if not st.session_state.llm_ready:
                configure_llm()
                st.session_state.llm_ready = True
            with st.spinner("Thinking..."):
                result = ask(df, question.strip())
            st.session_state.history.append(result)

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

    # Export buttons land here in the next step (PDF via WeasyPrint, Word via python-docx)
    st.button("Export Report (coming next)", disabled=True)
