#!/usr/bin/env bash
# Count candidate regex matches by label using grep -E and awk.
# Input CSV must have columns: text, fraudulent (0=genuine, 1=fraudulent).
set -euo pipefail
cd "$(dirname "$0")/.."
CSV="${1:-data/processed/emscad_dev.csv}"
if [[ ! -f "$CSV" ]]; then echo "CSV not found: $CSV" >&2; exit 1; fi
TMP="$(mktemp)"; trap 'rm -f "$TMP"' EXIT
python - "$CSV" > "$TMP" <<'PY'
import csv, sys, re
path=sys.argv[1]
with open(path, newline='', encoding='utf-8-sig') as f:
    reader=csv.DictReader(f)
    if not reader.fieldnames or 'fraudulent' not in reader.fieldnames:
        raise SystemExit("CSV needs a 'fraudulent' label column")
    # Prefer a combined text field if present; otherwise combine common EMSCAD fields.
    for row in reader:
        label=str(row.get('fraudulent','')).strip()
        if label not in {'0','1'}: continue
        text=row.get('text')
        if text is None:
            text=' '.join(str(row.get(k) or '') for k in ['title','company_profile','description','requirements','benefits'])
        text=re.sub(r'\s+',' ',str(text)).replace('\t',' ')
        print(label+'\t'+text)
PY
printf 'rule\tfraud_matches\tgenuine_matches\n'
while IFS='|' read -r name pattern; do
  [[ -z "$name" ]] && continue
  fraud=$(grep -icE $'^1\t.*('"$pattern"')' "$TMP" || true)
  genuine=$(grep -icE $'^0\t.*('"$pattern"')' "$TMP" || true)
  printf '%s\t%s\t%s\n' "$name" "$fraud" "$genuine"
done <<'RULES'
payment_fee|registration fee|security deposit|training fee|joining fee
external_messaging|whatsapp|telegram|wa\.me|t\.me
unrealistic_pay|earn.{0,30}(per day|daily)|guaranteed income
upfront_sensitive_data|aadhaar|pan card|bank account|otp
urgency|limited seats|join today|offer expires
RULES
