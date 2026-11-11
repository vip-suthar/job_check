#!/usr/bin/env bash
# Count how often candidate red-flag patterns appear in fraudulent vs genuine EMSCAD rows.
# Usage: scripts/prototype_rules.sh [csv]   (default: the training split, never the test split)
set -eu
cd "$(dirname "$0")/.."
INPUT="${1:-data/processed/emscad_train.csv}"
PYTHON="${PYTHON:-python3}"

PATTERNS=(
  "registration fee|security deposit|training fee|joining fee|processing fee"
  "wa\.me/|t\.me/|whats ?app|telegram"
  "per day|daily payout|daily payment|weekly payout"
  "earn (up to |upto )?(rs\.? ?|inr ?|₹ ?|\\$)[0-9]"
  "work from home|work at home|home based"
  "aadhaar|aadhar|pan card|bank account|bank details|otp"
  "@(gmail|yahoo|hotmail|outlook|rediffmail)\.com"
  "limited (seats|slots|vacancies)|join today|apply immediately|urgent(ly)? (hiring|requirement)"
  "no experience (needed|required)|no interview"
  "like and subscribe|rate products|online tasks|data entry"
  "part[ -]time"
  "money transfer|wire transfer|payroll processing"
  "unlimited (income|earning)|be your own boss|financial freedom"
)

if [ ! -f "$INPUT" ]; then
  echo "Dataset not found: $INPUT (run prepare_emscad.py first, or pass a CSV path)" >&2
  exit 1
fi

FLAT="$(mktemp)"
trap 'rm -f "$FLAT"' EXIT

# One line per posting: label<TAB>lower-cased text fields
"$PYTHON" - "$INPUT" > "$FLAT" <<'EOF'
import csv, sys
cols = ("title", "company_profile", "description", "requirements", "benefits")
for row in csv.DictReader(open(sys.argv[1], encoding="utf-8")):
    text = " ".join(row.get(c) or "" for c in cols)
    print(row["fraudulent"] + "\t" + " ".join(text.lower().split()))
EOF

FRAUD=$(awk -F'\t' '$1 == 1' "$FLAT" | wc -l | tr -d ' ')
GENUINE=$(awk -F'\t' '$1 == 0' "$FLAT" | wc -l | tr -d ' ')
if [ "$FRAUD" -eq 0 ] || [ "$GENUINE" -eq 0 ]; then
  echo "Need both fraudulent and genuine rows (got $FRAUD and $GENUINE)" >&2
  exit 1
fi

echo "Input: $INPUT ($FRAUD fraudulent, $GENUINE genuine)"
printf "%8s %9s %7s  %s\n" "fraud%" "genuine%" "ratio" "pattern"
for pattern in "${PATTERNS[@]}"; do
  grep -E -- "$pattern" "$FLAT" |
    P="$pattern" awk -F'\t' -v f="$FRAUD" -v g="$GENUINE" '
      { n[$1]++ }
      END {
        fp = 100 * n[1] / f; gp = 100 * n[0] / g
        ratio = gp ? sprintf("%.1f", fp / gp) : (fp ? "inf" : "0.0")
        printf "%8.2f %9.2f %7s  %s\n", fp, gp, ratio, ENVIRON["P"]
      }'
done | sort -k3,3gr
