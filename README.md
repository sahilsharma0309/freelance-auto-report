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
- **WeasyPrint** for branded PDF export *(coming next)*
- **python-docx** for branded Word export *(coming next)*

## Setup

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# then edit .env and paste your Groq API key (free at console.groq.com/keys)
```

> WeasyPrint needs system libraries on Linux:
> `sudo apt-get install libpango-1.0-0 libpangocairo-1.0-0 libcairo2`.
> On macOS: `brew install pango`.

## Run

```bash
streamlit run app.py
```

1. Upload a `.csv` / `.xlsx` / `.xls` file
2. Type a question, e.g. *"Plot monthly revenue by region as a bar chart"*
3. Get the chart + a written insight; results stack up as a session history

Uploaded files and generated charts are written to `uploads/` and `exports/`,
both git-ignored — client data never gets committed.

## Roadmap

- [x] Step 1 — project skeleton (`requirements.txt`, `.env.example`, `.gitignore`)
- [x] Step 2 — MVP: upload → PandasAI Q&A → chart in Streamlit
- [ ] Step 3 — branded PDF export (WeasyPrint HTML/CSS template)
- [ ] Step 4 — branded Word export (python-docx template)
