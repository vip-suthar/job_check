#!/usr/bin/env bash
# Rotate logs/*.log files above a size limit: app.log -> app.log.1 -> app.log.2 ...
# The app uses WatchedFileHandler, so it reopens app.log after the rename.
# Usage: scripts/rotate_logs.sh [max_kb] [keep]   (defaults: 1024 KB, keep 5)
set -eu
cd "$(dirname "$0")/.."
MAX_KB="${1:-1024}"
KEEP="${2:-5}"

case "$MAX_KB$KEEP" in
  *[!0-9]*) echo "max_kb and keep must be numbers" >&2; exit 1 ;;
esac
if [ "$KEEP" -lt 1 ]; then
  echo "keep must be at least 1" >&2
  exit 1
fi

rotate() {
  local log="$1" i
  rm -f "$log.$KEEP"
  for ((i = KEEP - 1; i >= 1; i--)); do
    if [ -f "$log.$i" ]; then
      mv "$log.$i" "$log.$((i + 1))"
    fi
  done
  mv "$log" "$log.1"
  echo "Rotated $log"
}

for log in logs/*.log; do
  [ -f "$log" ] || continue
  size_kb=$(( $(wc -c < "$log") / 1024 ))
  if [ "$size_kb" -ge "$MAX_KB" ]; then
    rotate "$log"
  fi
done
