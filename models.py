"""
models.py
Defines the core data classes used throughout the Asset Tracking System.
"""

from datetime import datetime


class Asset:
    """Represents a single piece of trackable equipment."""

    def __init__(self, asset_id, name, category, quantity=1,
                 status="Available", current_holder=None,
                 low_stock_threshold=1, date_added=None):
        self.asset_id = asset_id
        self.name = name
        self.category = category
        self.quantity = quantity
        self.status = status                      # "Available" or "Checked Out"
        self.current_holder = current_holder       # None if available
        self.low_stock_threshold = low_stock_threshold
        self.date_added = date_added or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def is_low_stock(self):
        return self.quantity <= self.low_stock_threshold

    def to_row(self):
        """Convert to a tuple matching the DB column order (for inserts)."""
        return (
            self.asset_id, self.name, self.category, self.quantity,
            self.status, self.current_holder, self.low_stock_threshold,
            self.date_added
        )

    @staticmethod
    def from_row(row):
        """Build an Asset object from a DB row tuple."""
        return Asset(
            asset_id=row[0], name=row[1], category=row[2], quantity=row[3],
            status=row[4], current_holder=row[5], low_stock_threshold=row[6],
            date_added=row[7]
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
