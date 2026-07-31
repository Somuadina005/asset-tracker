"""
tracker.py
Core business logic for the Asset Tracking System.
This is the class the CLI (or any future UI) talks to — it enforces
the rules (can't check out what's already out, can't check in what's
already in, low-stock detection, etc.) and delegates persistence to Database.
"""

from models import Asset, LogEntry
from database import Database


class AssetTracker:
    def __init__(self, db_path="asset_tracker.db"):
        self.db = Database(db_path)

    # ---------- Add equipment ----------

    def add_equipment(self, asset_id, name, category, quantity=1, low_stock_threshold=1,
                      department=None, purchase_date=None, warranty_expiration=None,
                      last_maintenance_date=None, repair_count=0):
        asset_id = asset_id.strip().upper()
        if self.db.asset_exists(asset_id):
            return False, f"Asset ID '{asset_id}' already exists."
        if quantity < 0 or low_stock_threshold < 0:
            return False, "Quantity and threshold must be non-negative."

        asset = Asset(
            asset_id=asset_id, name=name, category=category,
            quantity=quantity, status="Available", current_holder=None,
            low_stock_threshold=low_stock_threshold,
            # Optional -- only used by the AI Copilot feature. Existing
            # callers (the CLI in main.py) don't pass these and get the
            # same behavior as before.
            department=department or None,
            purchase_date=purchase_date or None,
            warranty_expiration=warranty_expiration or None,
            last_maintenance_date=last_maintenance_date or None,
            repair_count=repair_count or 0,
        )
        self.db.add_asset(asset)
        return True, f"Added asset '{name}' with ID {asset_id}."

    # ---------- Check out / check in ----------

    def check_out(self, asset_id, holder):
        asset_id = asset_id.strip().upper()
        asset = self.db.get_asset(asset_id)
        if not asset:
            return False, f"No asset found with ID {asset_id}."
        if asset.status == "Checked Out":
            return False, f"Asset {asset_id} is already checked out to {asset.current_holder}."
        if asset.quantity <= 0:
            return False, f"Asset {asset_id} has no units available to check out."

        self.db.update_asset_status(asset_id, "Checked Out", holder)
        self.db.adjust_quantity(asset_id, -1)
        self.db.add_log(LogEntry(asset_id, "CHECK_OUT", holder))

        updated = self.db.get_asset(asset_id)
        msg = f"Checked out {updated.name} ({asset_id}) to {holder}."
        if updated.is_low_stock():
            msg += f"  ⚠ LOW STOCK WARNING: only {updated.quantity} left."
        return True, msg

    def check_in(self, asset_id):
        asset_id = asset_id.strip().upper()
        asset = self.db.get_asset(asset_id)
        if not asset:
            return False, f"No asset found with ID {asset_id}."
        if asset.status == "Available":
            return False, f"Asset {asset_id} is already checked in."

        holder = asset.current_holder
        self.db.update_asset_status(asset_id, "Available", None)
        self.db.adjust_quantity(asset_id, 1)
        self.db.add_log(LogEntry(asset_id, "CHECK_IN", holder))
        return True, f"Checked in {asset.name} ({asset_id}) from {holder}."

    # ---------- Search ----------

    def search_by_id(self, asset_id):
        return self.db.search_by_id(asset_id.strip().upper())

    def search_by_name(self, keyword):
        return self.db.search_by_name(keyword.strip())

    # ---------- Alerts ----------

    def get_low_stock_alerts(self):
        return self.db.get_low_stock_assets()

    def get_open_notifications(self):
        """Notifications the background notification_service.py has flagged
        as unresolved -- includes how long they've been open and how many
        times the operator was already reminded."""
        return self.db.get_open_notifications_with_details()

    def get_notification_history(self, limit=100):
        """Full notification center feed: open + resolved, most recent first."""
        return self.db.get_notification_history(limit=limit)

    # ---------- Listing ----------

    def list_all_assets(self):
        return self.db.get_all_assets()

    # ---------- Reporting hooks ----------

    def get_logs_for_asset(self, asset_id):
        return self.db.get_logs_for_asset(asset_id.strip().upper())

    def get_all_logs(self):
        return self.db.get_all_logs()

    # ---------- AI copilot support ----------

    def get_checkout_counts(self):
        """Lifetime checkout count per asset_id. Used by ai_service.py
        (e.g. "most checked-out equipment" questions) instead of
        re-deriving it from raw logs independently."""
        return self.db.get_checkout_counts()

    def close(self):
        self.db.close()
