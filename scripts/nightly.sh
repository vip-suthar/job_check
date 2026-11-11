#!/usr/bin/env bash
# Nightly automation: scrape permitted sources, back up the database, rotate logs,
# and build the monthly Excel report on the 1st of each month.
# Schedule with cron (crontab -e), e.g. every night at 02:00:
#   0 2 * * * /full/path/to/job_check/scripts/nightly.sh >> /full/path/to/job_check/logs/nightly.log 2>&1
set -u
cd "$(dirname "$0")/.."
PYTHON="${PYTHON:-.venv/bin/python}"
FAILED=0

run() {
  echo "[$(date '+%F %T')] START $*"
  if "$@"; then
    echo "[$(date '+%F %T')] OK $*"
  else
    echo "[$(date '+%F %T')] FAILED $*"
    FAILED=1
  fi
}

if [ ! -x "$PYTHON" ]; then
  echo "Python not found at $PYTHON (run scripts/setup.sh first)" >&2
  exit 1
fi

# One file per night, so repeated runs never duplicate rows in earlier files
run "$PYTHON" scrape_pages.py --output "data/raw/scraped_$(date +%F).csv"
run scripts/backup.sh
run scripts/rotate_logs.sh
if [ "$(date +%d)" = "01" ]; then
  run "$PYTHON" -m scripts.monthly_report
fi

exit "$FAILED"
