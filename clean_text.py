#!/usr/bin/env python3
"""Basic whitespace and HTML-entity clean-up for scraped CSV text."""
import argparse
import html
import re
import pandas as pd

def clean(value):
    if pd.isna(value):
        return ""
    value = html.unescape(str(value))
    value = re.sub(r"\s+", " ", value)
    return value.strip()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_csv")
    parser.add_argument("output_csv")
    args = parser.parse_args()
    df = pd.read_csv(args.input_csv).fillna("")
    for col in ("title", "text"):
        if col in df.columns:
            df[col] = df[col].map(clean)
    df.to_csv(args.output_csv, index=False)
    print(f"Cleaned {len(df)} row(s): {args.output_csv}")

if __name__ == "__main__":
    main()
