#!/usr/bin/env bash
# Make a timestamped tar backup of the SQLite database and keep only the newest ones.
# Usage: scripts/backup.sh [keep]   (default: keep 7)
set -eu
cd "$(dirname "$0")/.."
DB="instance/jobcheck.db"
KEEP="${1:-7}"

case "$KEEP" in
  ''|*[!0-9]*|0) echo "keep must be a positive number" >&2; exit 1 ;;
esac
if [ ! -f "$DB" ]; then
  echo "No database at $DB, nothing to back up"
  exit 0
fi

mkdir -p backups
STAMP="$(date +%Y%m%d_%H%M%S)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# .backup gives a consistent copy even while the app is writing
sqlite3 "$DB" ".backup '$TMP/jobcheck.db'"
tar -czf "backups/jobcheck_$STAMP.tar.gz" -C "$TMP" jobcheck.db
echo "Backup written: backups/jobcheck_$STAMP.tar.gz"

ls -1t backups/jobcheck_*.tar.gz | tail -n +"$((KEEP + 1))" |
while read -r old; do
  rm -f -- "$old"
  echo "Removed old backup: $old"
done
