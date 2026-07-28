"""
notification_service.py
Standalone, decoupled notification worker for the Asset Tracking System.

Design goals
------------
- No AI/ML anywhere in this file. Just threshold checks + scheduling rules.
- Fully decoupled from the Flask app: it talks to the same SQLite file
  directly through Database/AssetTracker, but it is its own OS process.
  You run it independently (cron job, Windows Task Scheduler, or a
  systemd timer) -- the web app never has to import or call this code,
  and this code never imports Flask.
- Idempotent per run: running it twice in the same day for the same
  asset will not double-notify, because state lives in the
  notification_log table, not in memory.

How it decides whether to notify
---------------------------------
1. Every run, it asks the DB for all assets currently at/under their
   low_stock_threshold (tracker.get_low_stock_alerts()).
2. New problem (no open notification_log row for that asset)
   -> notify immediately, open a tracking row.
3. Ongoing problem (there IS an open row)
   -> only re-notify if enough time has passed since the last reminder.
      The interval grows the longer the issue sits unresolved
      (1 day -> 2 -> 4 -> 7, then holds at 7), UNLESS the asset is
      completely out of stock (quantity <= 0), in which case it always
      reminds daily -- an empty shelf doesn't get to "cool down".
      This is what stops the operator from getting the same "low on
      USB cables" email every single day forever.
4. Resolved problem (asset no longer low stock but has an open row)
   -> send a "resolved" notice and close the row, so if it dips low
      again later it's treated as a fresh issue (starts back at a
      1-day interval).

Usage
-----
    python3 notification_service.py --once      # single check, for cron
    python3 notification_service.py --loop       # runs forever, checks ~daily
    python3 notification_service.py --once --notifier console

Suggested cron entry (checks once a day at 8am):
    0 8 * * * cd /path/to/asset-tracker && /usr/bin/python3 notification_service.py --once >> notifications.log 2>&1

Suggested systemd timer is documented in README_NOTIFICATIONS.md.
"""

import argparse
import logging
import os
import smtplib
import time
from abc import ABC, abstractmethod
from datetime import datetime
from email.mime.text import MIMEText

from tracker import AssetTracker

# Escalation schedule, in days between reminders, indexed by escalation_level.
# Holds at the last value once escalation_level exceeds the list length.
REMINDER_SCHEDULE_DAYS = [1, 2, 4, 7]
CRITICAL_REMINDER_DAYS = 1  # out-of-stock items always remind at this cadence
CHECK_INTERVAL_SECONDS = 24 * 60 * 60  # how often --loop wakes up (~daily)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("notifications.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("notification_service")


# ---------------------------------------------------------------------------
# Notifier backends -- swap freely, no AI involved in any of them.
# ---------------------------------------------------------------------------

class Notifier(ABC):
    @abstractmethod
    def send(self, subject: str, body: str):
        ...


class ConsoleNotifier(Notifier):
    """Default backend: just logs. Safe to use with zero configuration."""

    def send(self, subject: str, body: str):
        log.info("NOTIFY -> %s\n%s", subject, body)


class EmailNotifier(Notifier):
    """
    Sends real email to the operator via SMTP.
    Configure with environment variables:
        SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, OPERATOR_EMAIL
    """

    def __init__(self):
        self.host = os.environ["SMTP_HOST"]
        self.port = int(os.environ.get("SMTP_PORT", "587"))
        self.user = os.environ["SMTP_USER"]
        self.password = os.environ["SMTP_PASS"]
        self.operator_email = os.environ["OPERATOR_EMAIL"]

    def send(self, subject: str, body: str):
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = self.user
        msg["To"] = self.operator_email
        with smtplib.SMTP(self.host, self.port) as server:
            server.starttls()
            server.login(self.user, self.password)
            server.send_message(msg)
        log.info("Email sent to %s: %s", self.operator_email, subject)


def build_notifier(name: str) -> Notifier:
    if name == "email":
        return EmailNotifier()
    return ConsoleNotifier()


# ---------------------------------------------------------------------------
# Core decision logic
# ---------------------------------------------------------------------------

def reminder_interval_days(escalation_level: int, quantity: int) -> int:
    """How many days must pass before the operator gets reminded again."""
    if quantity <= 0:
        return CRITICAL_REMINDER_DAYS
    idx = min(escalation_level, len(REMINDER_SCHEDULE_DAYS) - 1)
    return REMINDER_SCHEDULE_DAYS[idx]


def days_between(iso_earlier: str, iso_later: datetime) -> float:
    earlier = datetime.strptime(iso_earlier, "%Y-%m-%d %H:%M:%S")
    return (iso_later - earlier).total_seconds() / 86400


def run_check(tracker: AssetTracker, notifier: Notifier, now: datetime = None):
    now = now or datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")
    db = tracker.db

    low_stock_ids = {a.asset_id for a in tracker.get_low_stock_alerts()}
    low_stock_by_id = {a.asset_id: a for a in tracker.get_low_stock_alerts()}

    # 1) Resolve anything that recovered since the last check.
    for row in db.get_all_open_notifications():
        notif_id, asset_id = row[0], row[1]
        if asset_id not in low_stock_ids:
            db.resolve_notification(notif_id, now_str)
            asset = db.get_asset(asset_id)
            name = asset.name if asset else asset_id
            notifier.send(
                f"[Asset Tracker] RESOLVED: {name} ({asset_id}) restocked",
                f"{name} ({asset_id}) is back above its low-stock threshold "
                f"as of {now_str}. No further reminders needed unless it "
                f"drops low again.",
            )
            log.info("Resolved notification for %s", asset_id)

    # 2) New or ongoing low-stock issues.
    for asset_id in low_stock_ids:
        asset = low_stock_by_id[asset_id]
        open_row = db.get_open_notification(asset_id)

        if open_row is None:
            # Brand new issue -> notify right away.
            db.open_notification(asset_id, now_str)
            notifier.send(
                f"[Asset Tracker] LOW STOCK: {asset.name} ({asset_id})",
                f"{asset.name} ({asset_id}) has dropped to {asset.quantity} "
                f"units, at or below its threshold of "
                f"{asset.low_stock_threshold}. Detected {now_str}.",
            )
            log.info("Opened new notification for %s", asset_id)
            continue

        # open_row columns: notif_id, asset_id, first_detected_at,
        #                    last_notified_at, times_notified,
        #                    escalation_level, resolved_at
        notif_id, _, first_detected_at, last_notified_at, times_notified, escalation_level, _ = open_row

        elapsed = days_between(last_notified_at, now)
        interval = reminder_interval_days(escalation_level, asset.quantity)

        if elapsed >= interval:
            new_level = escalation_level + 1
            days_open = round(days_between(first_detected_at, now), 1)
            db.record_reminder(notif_id, now_str, new_level)
            notifier.send(
                f"[Asset Tracker] REMINDER: {asset.name} ({asset_id}) still low",
                f"{asset.name} ({asset_id}) has been below threshold for "
                f"{days_open} day(s) (currently {asset.quantity} units, "
                f"threshold {asset.low_stock_threshold}). This is reminder "
                f"#{times_notified + 1}. Next reminder in "
                f"{reminder_interval_days(new_level, asset.quantity)} day(s) "
                f"if still unresolved.",
            )
            log.info("Sent reminder #%d for %s", times_notified + 1, asset_id)
        else:
            log.info(
                "Skipping %s: reminded %.1f day(s) ago, next in %.1f day(s)",
                asset_id, elapsed, interval - elapsed,
            )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Asset Tracker notification worker")
    parser.add_argument("--db", default="asset_tracker.db", help="Path to the SQLite DB file")
    parser.add_argument("--notifier", choices=["console", "email"], default="console")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--once", action="store_true", help="Run a single check and exit (use with cron)")
    mode.add_argument("--loop", action="store_true", help="Run forever, checking roughly once a day")
    args = parser.parse_args()

    tracker = AssetTracker(db_path=args.db)
    notifier = build_notifier(args.notifier)

    if args.once:
        run_check(tracker, notifier)
        tracker.close()
        return

    log.info("Notification service started in loop mode (~daily checks).")
    try:
        while True:
            run_check(tracker, notifier)
            time.sleep(CHECK_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        log.info("Notification service stopped.")
    finally:
        tracker.close()


if __name__ == "__main__":
    main()
