"""PandasAI wrapper: load a data file, ask questions, normalize responses.

Keeps all pandasai specifics out of the Streamlit layer so the export
modules (PDF/Word) can reuse the same AnalysisResult objects later.
"""

import re
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
    # Interactive plotly figure for in-app display; exports use chart_path
    figure: object | None = field(default=None, repr=False)
    # Plain-language "how to read this chart" line for non-technical readers
    guide: str = ""
    # Report ordering: lower comes first (autoviz charts 1-8, Q&A answers 9)
    priority: int = 9


def story_order(results: list["AnalysisResult"]) -> list["AnalysisResult"]:
    """Order results the way a report should read: overview charts first
    (trend, growth, comparisons, breakdowns...), Q&A answers at the end."""
    return sorted(results, key=lambda r: r.priority)


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


def to_chat_frame(df: pd.DataFrame) -> pai.DataFrame:
    """Wrap a (possibly filtered) pandas frame for PandasAI chat."""
    return df if isinstance(df, pai.DataFrame) else pai.DataFrame(df)


def load_dataframe(path: str | Path) -> pai.DataFrame:
    """Load a CSV/Excel file into a PandasAI dataframe."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pai.read_csv(str(path))
    if suffix in (".xlsx", ".xls"):
        return pai.DataFrame(pd.read_excel(path))
    raise ValueError(f"Unsupported file type: {suffix} (use .csv, .xlsx or .xls)")


FRIENDLY_RATE_LIMIT_MESSAGE = (
    "⏳ The AI is busy right now (free-plan limit reached for this minute). "
    "Wait about a minute and press Analyze again — or use the Dashboard tab, "
    "which builds all charts without any AI."
)


def _chat_with_retry(df: pai.DataFrame, prompt: str, attempts: int = 4):
    """df.chat that waits out Groq free-tier rate limits instead of failing.

    Groq's error message includes "Please try again in Xs"; honor it,
    with a cap so a huge suggested wait can't hang the UI.
    """
    for attempt in range(attempts):
        try:
            return df.chat(prompt)
        except Exception as exc:
            message = str(exc)
            is_rate_limit = (
                "RateLimitError" in type(exc).__name__ or "rate_limit" in message
            )
            # "No code found" = the LLM answered without a code block; a
            # simple re-ask usually fixes it.
            is_flaky_output = "No code found" in message
            if not (is_rate_limit or is_flaky_output) or attempt == attempts - 1:
                raise
            if is_rate_limit:
                match = re.search(r"try again in ([\d.]+)s", message)
                wait = float(match.group(1)) + 1 if match else 20
                time.sleep(min(wait, 65))


def ask(df: pai.DataFrame, question: str) -> AnalysisResult:
    """Run one natural-language question and normalize the response.

    When the answer is a chart, a short follow-up question is asked so every
    chart also carries a written insight for the report.
    """
    try:
        response = _chat_with_retry(df, question)
    except Exception as exc:  # pandasai raises many provider-specific errors
        message = str(exc)
        if "RateLimitError" in type(exc).__name__ or "rate_limit" in message:
            message = FRIENDLY_RATE_LIMIT_MESSAGE
        return AnalysisResult(question=question, kind="error", text=message)

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
        follow_up = _chat_with_retry(df, prompt)
        if getattr(follow_up, "type", "") in ("string", "number"):
            return str(follow_up.value)
    except Exception:
        pass
    return ""
