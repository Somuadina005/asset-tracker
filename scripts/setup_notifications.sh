#!/usr/bin/env bash
#
# setup_notifications.sh
# One-command installer for the Asset Tracker notification service.
# Run this ON THE MACHINE where the app actually lives (your laptop,
# server, or VM) -- it wires up a daily cron job for you. It does NOT
# run from anywhere else, since it needs to know the real path to the
# repo and the real python3 on that machine.
#
# Usage:
#   ./scripts/setup_notifications.sh              # console notifier, 8am daily
#   ./scripts/setup_notifications.sh --time 07:30  # custom time
#   ./scripts/setup_notifications.sh --email       # use SMTP env vars instead
#
# Safe to re-run: it replaces any previous entry it installed instead
# of duplicating it (tagged with a unique marker comment).

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="$(command -v python3)"
TIME="08:00"
NOTIFIER="console"
MARKER="# ASSET_TRACKER_NOTIFICATION_SERVICE"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --time) TIME="$2"; shift 2 ;;
    --email) NOTIFIER="email"; shift ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

HOUR="${TIME%%:*}"
MIN="${TIME##*:}"

if [[ "$NOTIFIER" == "email" ]]; then
  for var in SMTP_HOST SMTP_PORT SMTP_USER SMTP_PASS OPERATOR_EMAIL; do
    if [[ -z "${!var:-}" ]]; then
      echo "ERROR: --email requires $var to be set in your environment first."
      echo "See README_NOTIFICATIONS.md for the full list."
      exit 1
    fi
  done
  CRON_CMD="cd $REPO_DIR && SMTP_HOST=$SMTP_HOST SMTP_PORT=$SMTP_PORT SMTP_USER=$SMTP_USER SMTP_PASS=$SMTP_PASS OPERATOR_EMAIL=$OPERATOR_EMAIL $PYTHON_BIN notification_service.py --once --notifier email >> notifications.log 2>&1"
else
  CRON_CMD="cd $REPO_DIR && $PYTHON_BIN notification_service.py --once --notifier console >> notifications.log 2>&1"
fi

CRON_LINE="$MIN $HOUR * * * $CRON_CMD $MARKER"

# Remove any previous entry this script installed, then add the new one.
{ crontab -l 2>/dev/null | grep -v "$MARKER" || true; echo "$CRON_LINE"; } | crontab -

echo "Installed. The notification service will run daily at $TIME using the '$NOTIFIER' notifier."
echo "Logs will be written to $REPO_DIR/notifications.log"
echo
echo "Verify with:  crontab -l"
echo "Test it right now with:  cd $REPO_DIR && $PYTHON_BIN notification_service.py --once"
echo "Remove it later with:    crontab -l | grep -v '$MARKER' | crontab -"
