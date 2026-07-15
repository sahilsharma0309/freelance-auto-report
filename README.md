# freelance-auto-report

Personal automated data-analysis tool for freelance data work: upload a
CSV/Excel file, ask a question in plain English, and get the right chart plus
a written insight — then export the whole thing as a branded PDF or Word
report. A lightweight replacement for Power BI/Tableau on freelance gigs.

## Stack

- **PandasAI v3** (`pai.read_csv` / `df.chat`) for natural-language analysis
  and auto chart generation
- **LiteLLM → Groq** as the LLM provider (free/cheap tier)
- **Streamlit** for the UI
- **WeasyPrint** for branded PDF export
- **python-docx** for branded Word export

## Setup

> **Requires Python 3.10 or 3.11.** PandasAI v3 does not support Python 3.12+
> yet. On Windows, install 3.11 from python.org and create the venv with
> `py -3.11 -m venv venv`.

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# then edit .env and paste your Groq API key (free at console.groq.com/keys)
```

> WeasyPrint needs system libraries:
> - **Linux (Debian/Ubuntu):** `sudo apt-get install $(cat packages.txt)`
> - **macOS:** `brew install pango`
> - **Windows:** install the [GTK3 runtime](https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases)
>
> On **Streamlit Community Cloud** no manual step is needed — `packages.txt`
> at the repo root is installed automatically, so PDF export just works.
> `runtime.txt` / `.python-version` pin Python 3.11 there; if the build
> still uses a newer Python, delete the app and redeploy choosing
> **Python 3.11** under Advanced settings (the version can't be changed
> on an existing app).

## Run

```bash
streamlit run app.py
```

1. Upload a `.csv` / `.xlsx` / `.xls` file
2. Type a question, e.g. *"Plot monthly revenue by region as a bar chart"*
3. Get the chart + a written insight; results stack up as a session history
4. Set a report title and download the whole session as a branded **PDF** or
   **Word** report

## Branding

All report branding lives in `core/branding.py` — name, navy/gold colors,
and the "Prepared by Sahil" footer watermark. Drop your logo at
`assets/logo.png` and it appears in the PDF header and Word header
automatically; until then reports show a navy/gold monogram.

Uploaded files and generated charts are written to `uploads/` and `exports/`,
both git-ignored — client data never gets committed.

## Roadmap

- [x] Step 1 — project skeleton (`requirements.txt`, `.env.example`, `.gitignore`)
- [x] Step 2 — MVP: upload → PandasAI Q&A → chart in Streamlit
- [x] Step 3 — branded PDF export (WeasyPrint HTML/CSS template)
- [x] Step 4 — branded Word export (python-docx template)
