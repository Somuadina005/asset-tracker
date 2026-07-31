"""
models.py
Defines the core data classes used throughout the Asset Tracking System.
"""

from datetime import datetime


class Asset:
    """Represents a single piece of trackable equipment."""

    def __init__(self, asset_id, name, category, quantity=1,
                 status="Available", current_holder=None,
                 low_stock_threshold=1, date_added=None,
                 # ---- Optional fields added for the AI Copilot feature.
                 # All default to "unknown" values so every existing caller
                 # (CLI, old tests, old rows in the DB) keeps working with
                 # zero changes. ----
                 department=None, purchase_date=None, warranty_expiration=None,
                 last_maintenance_date=None, repair_count=0):
        self.asset_id = asset_id
        self.name = name
        self.category = category
        self.quantity = quantity
        self.status = status                      # "Available" or "Checked Out"
        self.current_holder = current_holder       # None if available
        self.low_stock_threshold = low_stock_threshold
        self.date_added = date_added or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Optional metadata used by the AI Copilot for department/warranty/
        # maintenance-aware answers. None means "not tracked for this asset yet".
        self.department = department
        # purchase_date is deliberately separate from date_added: date_added
        # is "when this record was entered into the tracker" (always "now"
        # for new rows), while purchase_date is "when the physical asset was
        # actually acquired".
        self.purchase_date = purchase_date                    # "YYYY-MM-DD" or None
        self.warranty_expiration = warranty_expiration        # "YYYY-MM-DD" or None
        self.last_maintenance_date = last_maintenance_date     # "YYYY-MM-DD" or None
        self.repair_count = repair_count or 0

    def is_low_stock(self):
        return self.quantity <= self.low_stock_threshold

    def to_row(self):
        """Convert to a tuple matching the INSERT column order in
        Database.add_asset."""
        return (
            self.asset_id, self.name, self.category, self.quantity,
            self.status, self.current_holder, self.low_stock_threshold,
            self.date_added, self.department, self.purchase_date,
            self.warranty_expiration, self.last_maintenance_date, self.repair_count
        )

    @staticmethod
    def from_row(row):
        """Build an Asset object from a `SELECT * FROM assets` row tuple.
        Column order matches CREATE TABLE followed by the ALTER TABLE
        migrations in database.py._migrate_schema(). Any trailing columns
        beyond repair_count (e.g. leftover health-score columns on
        databases created before that feature was removed) are ignored."""
        return Asset(
            asset_id=row[0], name=row[1], category=row[2], quantity=row[3],
            status=row[4], current_holder=row[5], low_stock_threshold=row[6],
            date_added=row[7], department=row[8], purchase_date=row[9],
            warranty_expiration=row[10], last_maintenance_date=row[11],
            repair_count=row[12]
        )

    def __str__(self):
        holder = self.current_holder if self.current_holder else "—"
        flag = " ⚠ LOW STOCK" if self.is_low_stock() else ""
        return (f"[{self.asset_id}] {self.name} ({self.category}) | "
                f"Qty: {self.quantity} | Status: {self.status} | "
                f"Holder: {holder}{flag}")


class LogEntry:
    """Represents a single check-in/check-out event, for usage reports."""

    def __init__(self, asset_id, action, holder, timestamp=None):
        self.asset_id = asset_id
        self.action = action          # "CHECK_OUT" or "CHECK_IN"
        self.holder = holder
        self.timestamp = timestamp or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def to_row(self):
        return (self.asset_id, self.action, self.holder, self.timestamp)

    @staticmethod
    def from_row(row):
        # row: (id, asset_id, action, holder, timestamp)
        return LogEntry(asset_id=row[1], action=row[2], holder=row[3], timestamp=row[4])

    def __str__(self):
        return f"{self.timestamp} | {self.action:10s} | Asset {self.asset_id} | {self.holder}"
