#!/usr/bin/env bash
# Basic data checks for the JobCheck project.
set -eu
TARGET="${1:-data/processed}"

echo "Files under $TARGET:"
find "$TARGET" -type f -maxdepth 3 -print

echo
echo "CSV headers / first lines:"
find "$TARGET" -type f -name '*.csv' -print0 |
while IFS= read -r -d '' file; do
  echo "--- $file"
  head -n 2 "$file"
done

echo
echo "Repeated source URLs (if source_url exists):"
find "$TARGET" -type f -name '*.csv' -print0 |
while IFS= read -r -d '' file; do
  if head -n 1 "$file" | grep -q 'source_url'; then
    awk -F',' 'NR>1 {print $3}' "$file" | sort | uniq -c | sort -nr | head
  fi
done
