#!/usr/bin/env python3
"""Merge the two independent labels of the Indian set and freeze its dev/test split.

Each input row needs text, label_1 and label_2 (1 = suspicious, 0 = genuine).
Rows where the labellers disagree keep the discussed `label` if it is 0 or 1,
and are dropped otherwise. The test file is never overwritten unless --force is given.
"""
from __future__ import annotations

import argparse
import csv
import random
from pathlib import Path

LABELS = ("0", "1")

def final_label(row: dict) -> str | None:
    first, second = (row.get("label_1") or "").strip(), (row.get("label_2") or "").strip()
    if first in LABELS and first == second:
        return first
    resolved = (row.get("label") or "").strip()
    return resolved if resolved in LABELS else None

def stratified_split(rows: list[dict], dev_share: float, seed: int) -> tuple[list[dict], list[dict]]:
    rng = random.Random(seed)
    dev, test = [], []
    for label in LABELS:
        group = [row for row in rows if row["label"] == label]
        rng.shuffle(group)
        cut = round(len(group) * dev_share)
        dev += group[:cut]
        test += group[cut:]
    return dev, test

def main() -> None:
    parser = argparse.ArgumentParser(description="Freeze the labelled Indian set into dev and test files.")
    parser.add_argument("--input", default="data/indian_labelled.csv")
    parser.add_argument("--output-dir", default="data/processed")
    parser.add_argument("--dev-share", type=float, default=0.4)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--force", action="store_true", help="Overwrite an existing frozen split")
    args = parser.parse_args()

    source = Path(args.input)
    if not source.exists():
        raise SystemExit(f"Labelled file not found: {source}")
    out = Path(args.output_dir)
    dev_file, test_file = out / "indian_dev.csv", out / "indian_test.csv"
    if test_file.exists() and not args.force:
        raise SystemExit(f"{test_file} is frozen. Use --force only if the team agreed to re-split.")

    with source.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        rows = list(reader)
    missing = {"text", "label_1", "label_2"} - set(fields)
    if missing:
        raise SystemExit(f"Missing column(s) {sorted(missing)}. Available columns: {fields}")
    if "label" not in fields:
        fields.append("label")

    both = [row for row in rows if row["label_1"].strip() in LABELS and row["label_2"].strip() in LABELS]
    agreed = sum(row["label_1"].strip() == row["label_2"].strip() for row in both)
    if both:
        print(f"Agreement: {agreed}/{len(both)} ({100 * agreed / len(both):.1f}%) of double-labelled rows")

    kept = []
    for row in rows:
        label = final_label(row)
        if label is not None:
            kept.append({**row, "label": label})
    print(f"Kept {len(kept)} row(s); dropped {len(rows) - len(kept)} unlabelled or unresolved row(s)")

    out.mkdir(parents=True, exist_ok=True)
    for path, part in zip((dev_file, test_file), stratified_split(kept, args.dev_share, args.seed)):
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(part)
        counts = {label: sum(row["label"] == label for row in part) for label in LABELS}
        print(f"{path}: {len(part)} rows; label counts={counts}")
    print("Do not open the test file until the final evaluation.")

if __name__ == "__main__":
    main()
