"""Generate (and optionally email) a branded report from a data file — headless.

Runs the same Auto-Visualize + KPI pipeline as the app, without Streamlit.
Schedule it weekly with Windows Task Scheduler or cron for automatic
client reports.

Usage:
  python scripts/weekly_report.py data/sales.csv
  python scripts/weekly_report.py data/sales.csv --title "Weekly Sales Report" \
      --client "Acme Corp" --to client@example.com

Email uses SMTP settings from .env (see .env.example): SMTP_USER and
SMTP_PASSWORD are required for --to; SMTP_HOST/SMTP_PORT default to Gmail
(smtp.gmail.com:587 — use a Gmail App Password, not your real password).
"""

import argparse
import os
import smtplib
import sys
from datetime import date
from email.message import EmailMessage
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

from core.autoviz import auto_visualize  # noqa: E402
from core.kpis import compute_kpis  # noqa: E402
from core.report_pdf import export_pdf  # noqa: E402
from core.settings import REPORTS_DIR  # noqa: E402


def load_data(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    if path.suffix.lower() in (".xlsx", ".xls"):
        return pd.read_excel(path)
    raise SystemExit(f"Unsupported file type: {path.suffix}")


def send_email(to_addr: str, subject: str, body: str, pdf_path: Path) -> None:
    host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER", "")
    password = os.getenv("SMTP_PASSWORD", "")
    if not user or not password:
        raise SystemExit("Set SMTP_USER and SMTP_PASSWORD in .env to send email.")

    message = EmailMessage()
    message["From"] = user
    message["To"] = to_addr
    message["Subject"] = subject
    message.set_content(body)
    message.add_attachment(
        pdf_path.read_bytes(), maintype="application", subtype="pdf",
        filename=pdf_path.name,
    )
    with smtplib.SMTP(host, port) as server:
        server.starttls()
        server.login(user, password)
        server.send_message(message)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a branded report headlessly.")
    parser.add_argument("data", help="Path to the CSV/Excel data file")
    parser.add_argument("--title", default="Weekly Data Report")
    parser.add_argument("--client", default="", help="Client name for 'Prepared for'")
    parser.add_argument("--to", default="", help="Email the PDF to this address")
    args = parser.parse_args()

    data_path = Path(args.data)
    df = load_data(data_path)
    print(f"Loaded {data_path.name}: {len(df):,} rows × {len(df.columns)} columns")

    results = auto_visualize(df)
    kpis = compute_kpis(df)
    print(f"Built {len(results)} charts, {len(kpis)} KPIs")

    pdf_bytes = export_pdf(results, args.title, data_path.name,
                           kpis=kpis, client_name=args.client)
    out_name = f"{args.title.replace(' ', '_')}_{date.today():%Y-%m-%d}.pdf"
    out_path = REPORTS_DIR / out_name
    out_path.write_bytes(pdf_bytes)
    print(f"Report saved: {out_path}")

    if args.to:
        body = f"Hi,\n\nPlease find attached the {args.title} ({date.today():%d %B %Y})."
        if args.client:
            body += f"\n\nPrepared for {args.client}."
        body += "\n\nBest regards,\nSahil Sharma"
        send_email(args.to, f"{args.title} — {date.today():%d %b %Y}", body, out_path)
        print(f"Emailed to {args.to}")


if __name__ == "__main__":
    main()
