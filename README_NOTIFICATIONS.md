# Notification service

`notification_service.py` is a **standalone, decoupled** worker. It does not
import Flask and the Flask app does not import it — they only share the
same SQLite file. It has **no AI/ML in it**; it's plain threshold checks and
a scheduling rule.

## What it does

Once a day it:
1. Finds every asset at or below its `low_stock_threshold`.
2. Sends a notification the *first* time an asset crosses that line.
3. If the asset is still low on a later run, it only reminds again once
   enough time has passed — the wait grows the longer it's unresolved
   (1 day → 2 → 4 → 7, then holds at 7 days), **except** items that hit
   zero quantity, which remind daily since that's urgent.
4. When an asset is restocked above threshold, it sends a "resolved"
   notice and clears the tracking row, so a future dip is treated fresh.

This state lives in a new `notification_log` table in `asset_tracker.db`,
so it survives restarts and doesn't depend on the process staying alive.

## Running it

```bash
# One-off check (what you want for cron / Task Scheduler)
python3 notification_service.py --once

# Or run it as a long-lived process that checks ~once every 24h
python3 notification_service.py --loop
```

By default it just logs to `notifications.log` and stdout
(`--notifier console`). To send real email to the operator:

```bash
export SMTP_HOST=smtp.yourprovider.com
export SMTP_PORT=587
export SMTP_USER=alerts@yourcompany.com
export SMTP_PASS=your-app-password
export OPERATOR_EMAIL=operator@yourcompany.com
python3 notification_service.py --once --notifier email
```

## Scheduling it (cron)

```
0 8 * * * cd /path/to/asset-tracker && /usr/bin/python3 notification_service.py --once --notifier email >> notifications.log 2>&1
```

## Scheduling it (systemd timer, alternative to cron)

`/etc/systemd/system/asset-notify.service`
```ini
[Unit]
Description=Asset Tracker notification check

[Service]
Type=oneshot
WorkingDirectory=/path/to/asset-tracker
ExecStart=/usr/bin/python3 notification_service.py --once --notifier email
```

`/etc/systemd/system/asset-notify.timer`
```ini
[Unit]
Description=Run Asset Tracker notification check daily

[Timer]
OnCalendar=*-*-* 08:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
sudo systemctl enable --now asset-notify.timer
```

## AI chatbot (separate feature)

The Flask app now has an `/chatbot` page (`chatbot.py`) that lets an
operator ask plain-English questions about current inventory. It's fully
separate from the notification worker above and requires
`ANTHROPIC_API_KEY` to be set. If it's not set, the page still loads and
just tells the operator the assistant isn't configured yet.
