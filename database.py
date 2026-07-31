"""
database.py
Handles all SQLite persistence for the Asset Tracking System.
Keeps SQL isolated from business logic / CLI code.
"""

import sqlite3
from models import Asset, LogEntry


class Database:
    def __init__(self, db_path="asset_tracker.db"):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._create_tables()
        self._migrate_schema()

    def _create_tables(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS assets (
                asset_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                category TEXT,
                quantity INTEGER NOT NULL DEFAULT 1,
                status TEXT NOT NULL DEFAULT 'Available',
                current_holder TEXT,
                low_stock_threshold INTEGER NOT NULL DEFAULT 1,
                date_added TEXT
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset_id TEXT NOT NULL,
                action TEXT NOT NULL,
                holder TEXT,
                timestamp TEXT,
                FOREIGN KEY (asset_id) REFERENCES assets(asset_id)
            )
        """)
        # Tracks the notification state for each asset that is currently
        # (or was recently) below its low-stock threshold. One open row
        # per asset at a time -- this is what lets the notification
        # service avoid re-alerting the operator every single day.
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS notification_log (
                notif_id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset_id TEXT NOT NULL,
                first_detected_at TEXT NOT NULL,
                last_notified_at TEXT NOT NULL,
                times_notified INTEGER NOT NULL DEFAULT 1,
                escalation_level INTEGER NOT NULL DEFAULT 0,
                resolved_at TEXT,
                FOREIGN KEY (asset_id) REFERENCES assets(asset_id)
            )
        """)
        self.conn.commit()

    def _migrate_schema(self):
        """Additive, idempotent migration for the AI Copilot's optional
        asset metadata (department, warranty, maintenance, repairs).

        Uses ALTER TABLE ... ADD COLUMN instead of touching the CREATE TABLE
        statement above so that:
          - existing databases (and the CLI app, which imports this same
            module) keep working unchanged.
          - re-running the app never errors on "column already exists" --
            we check PRAGMA table_info first.

        New columns are all nullable / zero-defaulted, so every pre-existing
        row is automatically backfilled with safe values and every existing
        query (SELECT *, to_row/from_row, etc.) keeps working -- the new
        columns simply appear at the end of the row tuple.
        """
        existing_cols = {
            row[1] for row in self.conn.execute("PRAGMA table_info(assets)")
        }
        new_columns = [
            ("department", "TEXT"),
            ("purchase_date", "TEXT"),
            ("warranty_expiration", "TEXT"),
            ("last_maintenance_date", "TEXT"),
            ("repair_count", "INTEGER NOT NULL DEFAULT 0"),
        ]
        for col_name, col_def in new_columns:
            if col_name not in existing_cols:
                self.conn.execute(f"ALTER TABLE assets ADD COLUMN {col_name} {col_def}")
        self.conn.commit()

    # ---------- Notification log ----------

    def get_open_notification(self, asset_id):
        """The unresolved notification row for this asset, if any."""
        cur = self.conn.execute(
            "SELECT * FROM notification_log WHERE asset_id = ? AND resolved_at IS NULL",
            (asset_id,)
        )
        return cur.fetchone()

    def open_notification(self, asset_id, detected_at):
        self.conn.execute(
            """INSERT INTO notification_log
               (asset_id, first_detected_at, last_notified_at, times_notified, escalation_level)
               VALUES (?, ?, ?, 1, 0)""",
            (asset_id, detected_at, detected_at)
        )
        self.conn.commit()

    def record_reminder(self, notif_id, notified_at, escalation_level):
        self.conn.execute(
            """UPDATE notification_log
               SET last_notified_at = ?, times_notified = times_notified + 1,
                   escalation_level = ?
               WHERE notif_id = ?""",
            (notified_at, escalation_level, notif_id)
        )
        self.conn.commit()

    def resolve_notification(self, notif_id, resolved_at):
        self.conn.execute(
            "UPDATE notification_log SET resolved_at = ? WHERE notif_id = ?",
            (resolved_at, notif_id)
        )
        self.conn.commit()

    def get_all_open_notifications(self):
        cur = self.conn.execute(
            "SELECT * FROM notification_log WHERE resolved_at IS NULL ORDER BY asset_id"
        )
        return cur.fetchall()

    def get_open_notifications_with_details(self):
        """Open notifications joined with the asset's current name/qty,
        for display in the web UI (e.g. a popup/banner)."""
        cur = self.conn.execute("""
            SELECT n.notif_id, n.asset_id, n.first_detected_at, n.last_notified_at,
                   n.times_notified, n.escalation_level, n.resolved_at,
                   a.name, a.quantity, a.low_stock_threshold
            FROM notification_log n
            JOIN assets a ON a.asset_id = n.asset_id
            WHERE n.resolved_at IS NULL
            ORDER BY n.first_detected_at
        """)
        cols = ["notif_id", "asset_id", "first_detected_at", "last_notified_at",
                "times_notified", "escalation_level", "resolved_at",
                "name", "quantity", "threshold"]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def get_notification_history(self, limit=100):
        """Every notification, open or resolved, most recent activity first.
        Powers the full notification center page."""
        cur = self.conn.execute("""
            SELECT n.notif_id, n.asset_id, n.first_detected_at, n.last_notified_at,
                   n.times_notified, n.escalation_level, n.resolved_at,
                   a.name, a.quantity, a.low_stock_threshold
            FROM notification_log n
            JOIN assets a ON a.asset_id = n.asset_id
            ORDER BY n.last_notified_at DESC
            LIMIT ?
        """, (limit,))
        cols = ["notif_id", "asset_id", "first_detected_at", "last_notified_at",
                "times_notified", "escalation_level", "resolved_at",
                "name", "quantity", "threshold"]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    # ---------- Asset CRUD ----------

    def add_asset(self, asset: Asset):
        self.conn.execute(
            """INSERT INTO assets
               (asset_id, name, category, quantity, status, current_holder,
                low_stock_threshold, date_added, department, purchase_date,
                warranty_expiration, last_maintenance_date, repair_count)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            asset.to_row()
        )
        self.conn.commit()

    def asset_exists(self, asset_id):
        cur = self.conn.execute("SELECT 1 FROM assets WHERE asset_id = ?", (asset_id,))
        return cur.fetchone() is not None

    def get_asset(self, asset_id):
        cur = self.conn.execute("SELECT * FROM assets WHERE asset_id = ?", (asset_id,))
        row = cur.fetchone()
        return Asset.from_row(row) if row else None

    def update_asset_status(self, asset_id, status, holder):
        self.conn.execute(
            "UPDATE assets SET status = ?, current_holder = ? WHERE asset_id = ?",
            (status, holder, asset_id)
        )
        self.conn.commit()

    def adjust_quantity(self, asset_id, delta):
        self.conn.execute(
            "UPDATE assets SET quantity = quantity + ? WHERE asset_id = ?",
            (delta, asset_id)
        )
        self.conn.commit()

    def get_all_assets(self):
        cur = self.conn.execute("SELECT * FROM assets ORDER BY asset_id")
        return [Asset.from_row(row) for row in cur.fetchall()]

    def search_by_id(self, asset_id):
        return self.get_asset(asset_id)

    def search_by_name(self, keyword):
        cur = self.conn.execute(
            "SELECT * FROM assets WHERE name LIKE ? ORDER BY asset_id",
            (f"%{keyword}%",)
        )
        return [Asset.from_row(row) for row in cur.fetchall()]

    def get_low_stock_assets(self):
        cur = self.conn.execute(
            "SELECT * FROM assets WHERE quantity <= low_stock_threshold ORDER BY asset_id"
        )
        return [Asset.from_row(row) for row in cur.fetchall()]

    # ---------- Checkout activity (used by AI copilot context) ----------

    def get_checkout_counts(self):
        """Lifetime checkout count per asset, in one query -- used instead of
        looping get_logs_for_asset() per asset when summarizing the whole
        inventory."""
        cur = self.conn.execute(
            "SELECT asset_id, COUNT(*) FROM logs WHERE action = 'CHECK_OUT' GROUP BY asset_id"
        )
        return {asset_id: count for asset_id, count in cur.fetchall()}

    # ---------- Logs ----------

    def add_log(self, log_entry: LogEntry):
        self.conn.execute(
            "INSERT INTO logs (asset_id, action, holder, timestamp) VALUES (?, ?, ?, ?)",
            log_entry.to_row()
        )
        self.conn.commit()

    def get_logs_for_asset(self, asset_id):
        cur = self.conn.execute(
            "SELECT * FROM logs WHERE asset_id = ? ORDER BY log_id", (asset_id,)
        )
        return [LogEntry.from_row(row) for row in cur.fetchall()]

    def get_all_logs(self):
        cur = self.conn.execute("SELECT * FROM logs ORDER BY log_id")
        return [LogEntry.from_row(row) for row in cur.fetchall()]

    def close(self):
        self.conn.close()
