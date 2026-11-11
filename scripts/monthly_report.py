#!/usr/bin/env python3
"""Write the monthly Excel report to reports/report_YYYY-MM.xlsx.

Run from the project root: python -m scripts.monthly_report [--month YYYY-MM]
The default is the previous month, so a run on the 1st covers the month that just ended.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
from pathlib import Path

from app import create_app
from app.excel import monthly_report

def main() -> None:
    last_month = (date.today().replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    parser = argparse.ArgumentParser(description="Build the monthly JobCheck Excel report.")
    parser.add_argument("--month", default=last_month, help="Month as YYYY-MM (default: previous month)")
    parser.add_argument("--output-dir", default="reports")
    args = parser.parse_args()
    try:
        month = datetime.strptime(args.month, "%Y-%m")
    except ValueError:
        raise SystemExit(f"Month must look like 2026-10, got: {args.month}")

    app = create_app()
    with app.app_context():
        wb = monthly_report(month.year, month.month)
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    path = output / f"report_{month:%Y-%m}.xlsx"
    wb.save(path)
    print(f"Saved monthly report to {path}")

if __name__ == "__main__":
    main()
