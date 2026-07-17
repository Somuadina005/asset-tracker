"""
reports.py
Generates usage reports from the tracker's log and asset data.
Reports can be printed to console and/or exported to a text file.
"""

from collections import Counter, defaultdict
from datetime import datetime


def build_usage_report(tracker):
    """Returns a formatted string report and also the raw stats dict."""
    logs = tracker.get_all_logs()
    assets = {a.asset_id: a for a in tracker.list_all_assets()}

    checkout_counts = Counter()
    holder_activity = defaultdict(int)

    for log in logs:
        if log.action == "CHECK_OUT":
            checkout_counts[log.asset_id] += 1
            holder_activity[log.holder] += 1

    lines = []
    lines.append("=" * 60)
    lines.append("ASSET USAGE REPORT")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("=" * 60)

    lines.append("\n-- Most Checked-Out Equipment --")
    if checkout_counts:
        for asset_id, count in checkout_counts.most_common():
            name = assets[asset_id].name if asset_id in assets else "(deleted)"
            lines.append(f"  {asset_id:10s} {name:25s} checked out {count} time(s)")
    else:
        lines.append("  No check-out activity yet.")

    lines.append("\n-- Activity by Holder --")
    if holder_activity:
        for holder, count in sorted(holder_activity.items(), key=lambda x: -x[1]):
            lines.append(f"  {holder:20s} {count} check-out(s)")
    else:
        lines.append("  No activity recorded yet.")

    lines.append("\n-- Currently Checked Out --")
    checked_out = [a for a in assets.values() if a.status == "Checked Out"]
    if checked_out:
        for a in checked_out:
            lines.append(f"  {a.asset_id:10s} {a.name:25s} -> {a.current_holder}")
    else:
        lines.append("  Nothing is currently checked out.")

    lines.append("\n-- Low Stock Alerts --")
    low_stock = tracker.get_low_stock_alerts()
    if low_stock:
        for a in low_stock:
            lines.append(f"  {a.asset_id:10s} {a.name:25s} qty={a.quantity} (threshold {a.low_stock_threshold})")
    else:
        lines.append("  All assets are above their low-stock threshold.")

    lines.append("=" * 60)
    return "\n".join(lines)


def export_report(tracker, filepath="usage_report.txt"):
    report_text = build_usage_report(tracker)
    with open(filepath, "w") as f:
        f.write(report_text)
    return filepath
