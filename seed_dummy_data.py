"""
seed_dummy_data.py
Populates the Asset Tracking System with realistic dummy data so the
dashboard, reports, and AI Copilot all have something meaningful to show
out of the box.

This goes through AssetTracker (the same business-logic layer app.py and
main.py use) rather than writing to SQLite directly, so every rule the app
normally enforces (duplicate IDs, quantity validation, checkout/checkin
state transitions) is respected -- the seeded data is guaranteed to be as
valid as anything entered by hand through the UI.

Usage
-----
    python3 seed_dummy_data.py            # seed asset_tracker.db (default)
    python3 seed_dummy_data.py --reset    # delete the DB file first, then seed
    python3 seed_dummy_data.py --db path/to/other.db

Safe to re-run: assets that already exist (by asset_id) are skipped instead
of erroring out, so running this twice just fills in whatever is missing.
"""

import argparse
import os
import random
from datetime import date, timedelta

from tracker import AssetTracker

random.seed(7)  # reproducible dummy data across runs

TODAY = date.today()


def _days_ago(n):
    return (TODAY - timedelta(days=n)).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Dummy asset catalog -- deliberately spans several departments, ages, and
# warranty/maintenance states so the AI Copilot's summaries look realistic
# (some low-stock, some checked out, a mix of warranty/repair history).
# ---------------------------------------------------------------------------
ASSETS = [
    # asset_id, name, category, quantity, threshold, department,
    # purchase_date (days ago), warranty (days ago -> negative if expired),
    # last_maintenance (days ago or None), repair_count
    ("AST-1001", "Dell Latitude 5540 Laptop",      "Laptop",        8, 2, "Engineering",  1500,  -120, 60,   1),
    ("AST-1002", "Dell Latitude 5540 Laptop",      "Laptop",        1, 2, "Engineering",  2600,  -600, None, 4),
    ("AST-1003", "MacBook Pro 14\" M3",             "Laptop",        5, 2, "Design",        300,   400,  30,   0),
    ("AST-1004", "HP LaserJet Pro M404",            "Printer",       2, 1, "Operations",   1800,  -300, 200,  2),
    ("AST-1005", "Epson WorkForce Pro Scanner",     "Scanner",       1, 1, "Operations",   2200,  -900, None, 5),
    ("AST-1006", "Cisco Catalyst 9200 Switch",      "Networking",    4, 1, "IT",           2000,   200, 90,   1),
    ("AST-1007", "Ubiquiti UniFi Access Point",     "Networking",   12, 3, "IT",            600,   500, 45,   0),
    ("AST-1008", "Logitech MX Master 3S Mouse",     "Peripheral",   20, 5, "Engineering",    120,   700, None, 0),
    ("AST-1009", "Dell UltraSharp 27\" Monitor",     "Monitor",      15, 4, "Engineering",    400,   500, None, 0),
    ("AST-1010", "Herman Miller Aeron Chair",       "Furniture",     6, 2, "Facilities",   2900,  -1200, None, 1),
    ("AST-1011", "Standing Desk (Electric)",        "Furniture",     3, 1, "Facilities",   1600,   -50, None, 0),
    ("AST-1012", "Yubikey 5C NFC",                  "Security",     25, 8, "IT",            250,   900, None, 0),
    ("AST-1013", "Fluke 87V Multimeter",            "Test Equip.",   2, 1, "Engineering",  3200,  -1500, 700, 3),
    ("AST-1014", "Zebra ZD421 Label Printer",       "Printer",       1, 1, "Operations",   1100,  -30, 15,   1),
    ("AST-1015", "Poly Studio Video Bar",           "Conferencing",  4, 1, "Facilities",    500,   600, 60,   0),
    ("AST-1016", "iPad Pro 12.9\" (Loaner)",        "Tablet",        3, 1, "Sales",         900,  -200, None, 2),
    ("AST-1017", "Barcode Scanner (Handheld)",      "Warehouse",     1, 2, "Operations",   2500,  -800, 400,  6),
    ("AST-1018", "APC Smart-UPS 1500VA",            "Power",         5, 2, "IT",           1300,   150, 180,  1),
]

# (asset_id, holder) -- currently checked out; leave the rest Available
CHECKOUTS = [
    ("AST-1002", "J. Ramirez"),
    ("AST-1005", "T. Nguyen"),
    ("AST-1013", "S. Patel"),
    ("AST-1016", "M. Chen"),
    ("AST-1017", "A. Osei"),
]

# Extra checkout/checkin cycles (asset_id, holder) purely to build up
# lifetime checkout-count history for reports and the AI Copilot's
# "most checked-out asset" answers. Each entry does one full
# checkout -> checkin round trip.
CHECKOUT_HISTORY_CYCLES = [
    ("AST-1001", "K. Brooks"), ("AST-1001", "D. Alvarez"), ("AST-1001", "K. Brooks"),
    ("AST-1003", "R. Kim"), ("AST-1003", "R. Kim"),
    ("AST-1006", "N. Falk"),
    ("AST-1009", "K. Brooks"), ("AST-1009", "D. Alvarez"),
    ("AST-1015", "N. Falk"), ("AST-1015", "R. Kim"), ("AST-1015", "N. Falk"),
]


def seed(db_path="asset_tracker.db", reset=False):
    if reset and os.path.exists(db_path):
        os.remove(db_path)
        print(f"Removed existing {db_path}")

    tracker = AssetTracker(db_path=db_path)

    added, skipped = 0, 0
    for (asset_id, name, category, qty, threshold, dept,
         purchased_days_ago, warranty_days_ago, maint_days_ago, repairs) in ASSETS:
        if tracker.db.asset_exists(asset_id):
            skipped += 1
            continue

        ok, msg = tracker.add_equipment(
            asset_id, name, category, quantity=qty, low_stock_threshold=threshold,
            department=dept,
            purchase_date=_days_ago(purchased_days_ago),
            warranty_expiration=_days_ago(warranty_days_ago),
            last_maintenance_date=_days_ago(maint_days_ago) if maint_days_ago else None,
            repair_count=repairs,
        )
        print(("Added " if ok else "Skipped ") + msg)
        added += 1 if ok else 0

    # Build up checkout-count history first (full round trips), then apply
    # the "currently checked out" set last so those stay Checked Out.
    for asset_id, holder in CHECKOUT_HISTORY_CYCLES:
        ok, msg = tracker.check_out(asset_id, holder)
        if ok:
            tracker.check_in(asset_id)

    for asset_id, holder in CHECKOUTS:
        ok, msg = tracker.check_out(asset_id, holder)
        print(("Checked out " if ok else "Could not check out ") + msg)

    print(f"\nSeeded {added} new asset(s), skipped {skipped} existing.")

    tracker.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed the Asset Tracking System with dummy data.")
    parser.add_argument("--db", default="asset_tracker.db", help="Path to the SQLite DB file.")
    parser.add_argument("--reset", action="store_true", help="Delete the DB file first, then seed fresh.")
    args = parser.parse_args()
    seed(db_path=args.db, reset=args.reset)
