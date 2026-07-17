# Asset Tracking System

A Python asset/equipment tracking system with SQLite persistence, available as
both a command-line tool and a Flask web app. Models the core workflow
companies, hospitals, and organizations use to track equipment check-out/check-in,
ownership, and inventory levels.

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
├── models.py         # Asset & LogEntry data classes
├── database.py       # SQLite persistence layer (all SQL lives here)
├── tracker.py         # AssetTracker — business rules, the layer any UI talks to
├── reports.py         # Usage report generation/aggregation
├── main.py            # CLI menu — entry point
├── app.py              # Flask web app — entry point
├── templates/          # Jinja2 templates for the web UI
├── static/style.css    # Web UI styling
└── README.md
```

This is a layered design on purpose: neither `main.py` (CLI) nor `app.py` (web)
touch SQL directly, `tracker.py` (business logic) doesn't know which UI is
calling it, and `database.py` never enforces rules — it just persists what
it's told. That separation is what let the web UI get added later (`app.py`)
without changing a single line of `tracker.py`, `database.py`, or `models.py`.

## How to run

### Command line

```bash
cd asset_tracker
python3 main.py
```

No external dependencies — uses only the Python standard library
(`sqlite3`, `collections`, `datetime`). A database file `asset_tracker.db`
is created automatically in the working directory on first run.

### Web app

```bash
cd asset_tracker
pip install -r requirements.txt
python3 app.py
```

Then open **http://127.0.0.1:5000**. Requires Flask (see `requirements.txt`);
everything else is still standard library. The web app reuses `tracker.py`,
`database.py`, `models.py`, and `reports.py` exactly as-is — it's a thin
Flask + Jinja2 layer on top of the same business logic the CLI uses, sharing
the same `asset_tracker.db` file.

**Web UI pages:**
- **Dashboard** — live stats, low-stock alerts, full equipment table with inline check-in
- **Add equipment** — register new assets
- **Asset detail** — per-asset check-out/check-in and full history
- **Search** — by Asset ID or name keyword
- **Usage report** — most-checked-out equipment, activity by holder, currently
  checked-out list, low-stock summary; exportable as `.txt`

## Design notes / known simplifications

- Each asset has **one** `status`/`current_holder` field even if `quantity > 1`.
  Checking out decrements quantity and marks the asset "Checked Out" once any
  unit is out — this matches "who currently has custody" tracking for
  single/small-quantity items (laptops, sensors, vehicles). For high-quantity
  consumables (e.g. 50 hard hats), you'd extend this to per-unit or bulk
  check-out records — a natural "v2" talking point in an interview.
- No authentication/multi-user layer — intentional for a scoped portfolio
  project; would be the first thing added for a real deployment.
