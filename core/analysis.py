"""PandasAI wrapper: load a data file, ask questions, normalize responses.

Keeps all pandasai specifics out of the Streamlit layer so the export
modules (PDF/Word) can reuse the same AnalysisResult objects later.
"""

import time
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import pandasai as pai
from pandasai_litellm.litellm import LiteLLM

from core.settings import CHARTS_DIR, GROQ_API_KEY, LLM_MODEL


@dataclass
class AnalysisResult:
    """One question/answer round, in a form both the UI and reports can render."""

    question: str
    kind: str  # "chart" | "dataframe" | "text" | "error"
    text: str = ""
    chart_path: str | None = None
    dataframe: pd.DataFrame | None = field(default=None, repr=False)


def configure_llm(api_key: str = "", model: str = "") -> None:
    """Point PandasAI at Groq through LiteLLM. Call once per session."""
    api_key = api_key or GROQ_API_KEY
    model = model or LLM_MODEL
    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY is not set. Copy .env.example to .env and add your key."
        )
    llm = LiteLLM(model=model, api_key=api_key)
    pai.config.set(
        {
            "llm": llm,
            "verbose": False,
            "save_logs": False,
            "max_retries": 3,
        }
    )


def load_dataframe(path: str | Path) -> pai.DataFrame:
    """Load a CSV/Excel file into a PandasAI dataframe."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pai.read_csv(str(path))
    if suffix in (".xlsx", ".xls"):
        return pai.DataFrame(pd.read_excel(path))
    raise ValueError(f"Unsupported file type: {suffix} (use .csv, .xlsx or .xls)")


def ask(df: pai.DataFrame, question: str) -> AnalysisResult:
    """Run one natural-language question and normalize the response.

    When the answer is a chart, a short follow-up question is asked so every
    chart also carries a written insight for the report.
    """
    try:
        response = df.chat(question)
    except Exception as exc:  # pandasai raises many provider-specific errors
        return AnalysisResult(question=question, kind="error", text=str(exc))

    rtype = getattr(response, "type", "string")

    if rtype == "chart":
        chart_path = CHARTS_DIR / f"chart_{int(time.time() * 1000)}.png"
        response.save(str(chart_path))
        return AnalysisResult(
            question=question,
            kind="chart",
            chart_path=str(chart_path),
            text=_written_insight(df, question),
        )

    if rtype == "dataframe":
        value = response.value
        frame = value if isinstance(value, pd.DataFrame) else pd.DataFrame(value)
        return AnalysisResult(question=question, kind="dataframe", dataframe=frame)

    return AnalysisResult(question=question, kind="text", text=str(response.value))


def _written_insight(df: pai.DataFrame, question: str) -> str:
    """Ask for a plain-text takeaway to pair with a chart."""
    prompt = (
        "Answer in plain text only, no chart or code: in 2-4 sentences, "
        f"summarize the key insight from the data for this question: {question}"
    )
    try:
        follow_up = df.chat(prompt)
        if getattr(follow_up, "type", "") in ("string", "number"):
            return str(follow_up.value)
    except Exception:
        pass
    return ""
