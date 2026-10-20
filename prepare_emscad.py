#!/usr/bin/env python3
"""Validate EMSCAD CSV and create reproducible stratified train/dev/test splits."""
from pathlib import Path
import argparse
import pandas as pd
from sklearn.model_selection import train_test_split

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', default=str(ROOT / 'data/raw/emscad.csv'))
    parser.add_argument('--label-column', default='fraudulent')
    parser.add_argument('--seed', type=int, default=42)
    args = parser.parse_args()
    source = Path(args.input)
    if not source.exists():
        raise SystemExit(f"Dataset not found: {source}\nDownload EMSCAD manually after checking its licence, then place its CSV here.")
    df = pd.read_csv(source, low_memory=False)
    if args.label_column not in df.columns:
        raise SystemExit(f"Label column '{args.label_column}' missing. Available columns: {list(df.columns)}")
    df = df.dropna(subset=[args.label_column]).drop_duplicates().copy()
    labels = pd.to_numeric(df[args.label_column], errors='coerce')
    if labels.isna().any() or not set(labels.unique()).issubset({0, 1}):
        raise SystemExit('Expected binary labels 0 (genuine) and 1 (fraudulent). Inspect and map labels explicitly.')
    df[args.label_column] = labels.astype(int)
    train, temp = train_test_split(df, test_size=.30, random_state=args.seed, stratify=df[args.label_column])
    dev, test = train_test_split(temp, test_size=.50, random_state=args.seed, stratify=temp[args.label_column])
    out = ROOT / 'data/processed'; out.mkdir(parents=True, exist_ok=True)
    for name, part in [('train', train), ('dev', dev), ('test', test)]:
        part.to_csv(out / f'emscad_{name}.csv', index=False)
        print(f'{name}: {len(part)} rows; label counts={part[args.label_column].value_counts().sort_index().to_dict()}')
    print(f'Wrote splits to {out}. Keep test split untouched until final evaluation.')

if __name__ == '__main__': main()
