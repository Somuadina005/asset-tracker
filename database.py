"""
database.py
Handles all SQLite persistence for the Asset Tracking System.
Keeps SQL isolated from business logic / CLI code.
"""

import sqlite3
from models import Asset, LogEntry


class Database:
    def __init__(self, db_path="asset_tracker.db"):
        self.conn = sqlite3.connect(db_path)
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._create_tables()

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
        self.conn.commit()

    # ---------- Asset CRUD ----------

    def add_asset(self, asset: Asset):
        self.conn.execute(
            """INSERT INTO assets
               (asset_id, name, category, quantity, status, current_holder,
                low_stock_threshold, date_added)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
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
