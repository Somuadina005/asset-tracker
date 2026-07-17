# Asset Tracking System

A command-line asset/equipment tracking system built in Python with SQLite persistence.
Models the core workflow companies, hospitals, and organizations use to track
equipment check-out/check-in, ownership, and inventory levels.

## Features

- **Add equipment** — register new assets with ID, name, category, quantity, and low-stock threshold
- **Check equipment in/out** — enforces rules (can't double-check-out, can't check in what's already in)
- **Track current holder** — always know who has what
- **Low inventory alerts** — flags assets at or below their configured threshold
- **Search by ID or name** — quick lookup, partial-match name search
- **Usage reports** — most-checked-out equipment, activity by holder, currently checked-out list,
  and low-stock summary; exportable to a `.txt` file

## Concepts demonstrated

| Concept       | Where                                                             |
|---------------|--------------------------------------------------------------------|
| OOP / Classes | `Asset`, `LogEntry`, `Database`, `AssetTracker`                   |
| File I/O      | SQLite database file (`asset_tracker.db`), text report export     |
| SQLite        | `database.py` — all persistence isolated from business logic      |
| Dictionaries (maps) | `reports.py` uses `Counter`/`defaultdict` to aggregate usage |
| Searching     | Exact ID lookup and `LIKE`-based keyword search                   |

## Architecture

```
asset_tracker/
├── models.py      # Asset & LogEntry data classes
├── database.py     # SQLite persistence layer (all SQL lives here)
├── tracker.py       # AssetTracker — business rules, the layer the UI talks to
├── reports.py       # Usage report generation/aggregation
├── main.py          # CLI menu — entry point
└── README.md
```

This is a layered design on purpose: `main.py` (UI) never touches SQL directly,
`tracker.py` (business logic) never touches the CLI, and `database.py` never
enforces rules — it just persists what it's told. That separation is what lets
you swap the CLI for a Flask API or web UI later without rewriting the logic.

## How to run

```bash
cd asset_tracker
python3 main.py
```

No external dependencies — uses only the Python standard library
(`sqlite3`, `collections`, `datetime`). A database file `asset_tracker.db`
is created automatically in the working directory on first run.

## Design notes / known simplifications

- Each asset has **one** `status`/`current_holder` field even if `quantity > 1`.
  Checking out decrements quantity and marks the asset "Checked Out" once any
  unit is out — this matches "who currently has custody" tracking for
  single/small-quantity items (laptops, sensors, vehicles). For high-quantity
  consumables (e.g. 50 hard hats), you'd extend this to per-unit or bulk
  check-out records — a natural "v2" talking point in an interview.
- No authentication/multi-user layer — intentional for a scoped portfolio
  project; would be the first thing added for a real deployment.
