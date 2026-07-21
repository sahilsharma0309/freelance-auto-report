# 📊 freelance-auto-report

> **Upload a CSV/Excel file → ask a question in plain English → get the right chart + a written insight → export it all as a branded PDF or Word report.** An AI data analyst that replaces manual Power BI/Tableau work on freelance gigs.

**🔗 Live demo:** [sahilsharma0309-freelance-auto-report-app-pgypzo.streamlit.app](https://sahilsharma0309-freelance-auto-report-app-pgypzo.streamlit.app/) &nbsp;·&nbsp; **⚙️ Stack:** Python · Streamlit · PandasAI v3 · Groq LLM · WeasyPrint

**Why it matters:** one upload replaces the whole manual loop — writing queries, building charts, and formatting a client-ready report by hand.

![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/Built%20with-Streamlit-FF4B4B?logo=streamlit&logoColor=white)
![Status](https://img.shields.io/badge/status-active-success)

---

## Stack

- **PandasAI v3** (`pai.read_csv` / `df.chat`) for natural-language analysis
  and auto chart generation
- **LiteLLM → Groq** as the LLM provider (free/cheap tier)
- **Streamlit** for the UI
- **WeasyPrint** for branded PDF export
- **python-docx** for branded Word export
- **pypdf** (AES-256) for optional PDF password protection

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
2. Click **Build dashboard** for an instant, LLM-free chart set, or type a
   question in **Ask AI**, e.g. *"Plot monthly revenue by region as a bar chart"*
3. Get the chart + a written insight; results stack up as a session history
4. Set a report title and download the whole session as a branded **PDF** or
   **Word** report — optionally password-protecting the PDF

## Campaign / marketing charts

The **Build dashboard** button auto-detects marketing-campaign data (channels,
campaigns, customer type, sales) and adds colorful, client-ready views on top of
the standard trend/growth/ranking charts:

- **Share donut** — each channel's or campaign's share of total sales
  (e.g. *Email 51% · Instagram 29% · Website Banner 20%*)
- **Grouped / stacked combo** — sales by one dimension split by another
  (e.g. *Sales by Channel, split by Campaign*), which answers the classic
  *"which campaign + channel combo should we double down on?"* question and
  automatically calls out the strongest combination and the leading segment

Colors use a fixed, colorblind-safe categorical palette; every chart carries
direct value labels so it stays readable in print and for non-technical clients.
All titles, insights and reading guides follow the sidebar language (English /
हिंदी).

## PDF password protection

On the **Export Report** tab, expand **🔒 Password-protect the PDF** to set an
optional password:

- **Leave it empty** → a normal PDF that opens without a password.
- **Set a password** → the PDF is encrypted with **AES-256 (PDF 2.0 / R6)** and
  opens only with that password, in any standard reader (Acrobat, Chrome,
  Preview, mobile). A strength meter helps you pick a password that holds up.

**How safe is it, honestly?** AES-256 with a *strong* password has no known
practical break — brute-forcing it is infeasible for any tool, so the password
itself is the real lock (there's no owner-password back door here). What no
standard PDF can do is *self-destruct* or erase itself if someone tries to crack
it on their own device — a PDF is passive data, so once a copy leaves your hands
nothing in the file can run to wipe it. Anyone promising a self-wiping PDF is
overselling. The genuine protection is **strong AES-256 encryption + a strong
passphrase**, which this gives you; the Word export is not encrypted.

## Branding

All report branding lives in `core/branding.py` — name, navy/gold colors,
and the "Prepared by Sahil" footer watermark. Drop your logo at
`assets/logo.png` and it appears in the PDF header and Word header
automatically; until then reports show a navy/gold monogram.

Uploaded files and generated charts are written to `uploads/` and `exports/`,
both git-ignored — client data never gets committed.

## Scheduled weekly reports (email)

`scripts/weekly_report.py` runs the whole pipeline headlessly — Auto-Visualize
charts, KPI cards, branded PDF — and can email the result:

```bash
python scripts/weekly_report.py data/sales.csv --title "Weekly Sales Report" \
    --client "Acme Corp" --to client@example.com
```

Set the `SMTP_*` values in `.env` first (for Gmail, use an App Password).
Schedule it weekly:

- **Windows** — Task Scheduler → Create Basic Task → weekly → Action:
  `C:\...\venv\Scripts\python.exe C:\...\scripts\weekly_report.py C:\...\data.csv --to client@example.com`
- **Linux/macOS** — `crontab -e` →
  `0 9 * * 1 cd /path/to/repo && venv/bin/python scripts/weekly_report.py data.csv --to client@example.com`

## Roadmap

- [x] Step 1 — project skeleton (`requirements.txt`, `.env.example`, `.gitignore`)
- [x] Step 2 — MVP: upload → PandasAI Q&A → chart in Streamlit
- [x] Step 3 — branded PDF export (WeasyPrint HTML/CSS template)
- [x] Step 4 — branded Word export (python-docx template)
- [x] Step 5 — colorful campaign charts (share donut + grouped/stacked combo)
- [x] Step 6 — optional AES-256 password protection for exported PDFs
