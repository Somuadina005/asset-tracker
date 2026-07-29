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
                 # ---- Optional fields added for the AI Copilot / health
                 # score features. All default to "unknown" values so every
                 # existing caller (CLI, old tests, old rows in the DB)
                 # keeps working with zero changes. ----
                 department=None, purchase_date=None, warranty_expiration=None,
                 last_maintenance_date=None, repair_count=0,
                 health_score=None, health_status=None,
                 health_recommendation=None, health_updated_at=None):
        self.asset_id = asset_id
        self.name = name
        self.category = category
        self.quantity = quantity
        self.status = status                      # "Available" or "Checked Out"
        self.current_holder = current_holder       # None if available
        self.low_stock_threshold = low_stock_threshold
        self.date_added = date_added or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Optional metadata used by the health-score model. None means
        # "not tracked for this asset yet" -- health_score_service.py treats
        # that as a neutral signal rather than a penalty.
        self.department = department
        # purchase_date is deliberately separate from date_added: date_added
        # is "when this record was entered into the tracker" (always "now"
        # for new rows), while purchase_date is "when the physical asset was
        # actually acquired" -- the one the health score's age factor should
        # use, since an old asset entered into the system today is still old.
        self.purchase_date = purchase_date                    # "YYYY-MM-DD" or None
        self.warranty_expiration = warranty_expiration        # "YYYY-MM-DD" or None
        self.last_maintenance_date = last_maintenance_date     # "YYYY-MM-DD" or None
        self.repair_count = repair_count or 0

        # Cached output of the last health-score run (see health_score_service.py).
        # None until recalculated at least once.
        self.health_score = health_score
        self.health_status = health_status
        self.health_recommendation = health_recommendation
        self.health_updated_at = health_updated_at

    def is_low_stock(self):
        return self.quantity <= self.low_stock_threshold

    def health_pill_class(self):
        """CSS class for the health-status pill (see style.css). Kept here
        rather than duplicated as if/elif chains in every template."""
        return {
            "Healthy": "pill-healthy",
            "Monitor": "pill-monitor",
            "Replace Soon": "pill-replace",
        }.get(self.health_status, "pill-alert")

    def to_row(self):
        """Convert to a tuple matching the INSERT column order in
        Database.add_asset (health fields aren't included here -- they
        start out NULL and are filled in later by health_score_service.py)."""
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
        migrations in database.py._migrate_schema()."""
        return Asset(
            asset_id=row[0], name=row[1], category=row[2], quantity=row[3],
            status=row[4], current_holder=row[5], low_stock_threshold=row[6],
            date_added=row[7], department=row[8], purchase_date=row[9],
            warranty_expiration=row[10], last_maintenance_date=row[11],
            repair_count=row[12], health_score=row[13], health_status=row[14],
            health_recommendation=row[15], health_updated_at=row[16]
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
