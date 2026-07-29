"""
health_score_service.py
Predictive Asset Health Score -- the ML half of the AI feature set.

Design goals
------------
- Fully isolated from the rest of the app: nothing else imports scikit-learn
  or numpy, so this module can be swapped out (or its model retrained on
  real data) without touching tracker.py, database.py, or app.py.
- No historical failure/repair-outcome data exists yet in this project, so
  the model is trained on *synthetic* examples generated from a documented
  heuristic (see `_heuristic_score` and `generate_synthetic_training_data`).
  When real data becomes available (e.g. a future `maintenance_events` or
  `failures` table), replace `generate_synthetic_training_data()` with a
  function that pulls real (features, outcome) pairs from the DB -- the
  rest of this module (feature extraction, scoring, recommendations)
  doesn't need to change.
- Read-only with respect to business rules: this module only *computes*
  scores. Persisting them is done through Database.update_asset_health(),
  which tracker.py/app.py already have access to.

Public API
----------
    recalculate_all(tracker) -> list[dict]
        Scores every asset in the system and writes the results back to
        the DB. This is what app.py calls (on a button click, or lazily
        when a dashboard visit finds unscored assets).

    scorer.score_asset(asset, checkout_count) -> (score, status, recommendation)
        Score a single asset without touching the DB. Useful for previews.
"""

from datetime import datetime, date

import numpy as np
from sklearn.ensemble import RandomForestRegressor

# ---------------------------------------------------------------------------
# Status thresholds -- kept as simple constants so they're easy to tune
# without digging through the model code.
# ---------------------------------------------------------------------------
HEALTHY_THRESHOLD = 75      # score >= this  -> "Healthy"
MONITOR_THRESHOLD = 40      # score >= this  -> "Monitor"; below -> "Replace Soon"

MAX_AGE_DAYS_FOR_SCORING = 365 * 8  # ages beyond this don't get penalized further
MAX_CHECKOUTS_FOR_SCORING = 60      # checkout counts beyond this saturate


def parse_date(value):
    """Best-effort parse of the date strings this app stores (either a
    plain 'YYYY-MM-DD' from a form, or a full 'YYYY-MM-DD HH:MM:SS'
    timestamp from date_added). Returns None if unparseable/missing.

    Public (not prefixed with _) because ai_service.py reuses it too, so
    the two services agree on what "expired"/"age" mean."""
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _heuristic_score(age_days, checkout_count, repair_count,
                      warranty_expired, has_maintenance_record, low_stock):
    """Deterministic rule-of-thumb health score (0-100), used only to
    label synthetic training examples. This encodes the same domain
    intuition a technician would apply by hand:
      - older assets and heavily-used assets wear down
      - frequent repairs are a strong signal of decline
      - an expired warranty compounds risk (no cheap fix if it breaks)
      - having *any* maintenance history is a mild positive (it means the
        asset is actually being looked after, not neglected)
      - low stock is a supply-chain signal, not a wear signal, so it only
        nudges the score slightly
    """
    score = 100.0
    score -= 35 * min(age_days / MAX_AGE_DAYS_FOR_SCORING, 1.0)
    score -= 20 * min(checkout_count / MAX_CHECKOUTS_FOR_SCORING, 1.0)
    score -= min(repair_count, 6) * 6
    if warranty_expired:
        score -= 8
    if not has_maintenance_record:
        score -= 5
    if low_stock:
        score -= 4
    return max(0.0, min(100.0, score))


def generate_synthetic_training_data(n=1200, seed=42):
    """Generate (features, label) pairs for training.

    NOTE: this is synthetic data standing in for real historical failure/
    repair records, which this project doesn't have yet. Swap this out for
    a real query (e.g. joining a future `failures` table against asset
    features at the time of failure) once that data exists -- the model
    class and scoring pipeline below don't need to change.
    """
    rng = np.random.default_rng(seed)
    age_days = rng.uniform(0, MAX_AGE_DAYS_FOR_SCORING * 1.2, n)
    checkout_count = rng.integers(0, MAX_CHECKOUTS_FOR_SCORING + 20, n)
    repair_count = rng.poisson(1.2, n)
    warranty_expired = rng.integers(0, 2, n)
    has_maintenance_record = rng.integers(0, 2, n)
    low_stock = rng.integers(0, 2, n)

    X = np.column_stack([
        age_days, checkout_count, repair_count,
        warranty_expired, has_maintenance_record, low_stock,
    ])
    y = np.array([
        _heuristic_score(*row) + rng.normal(0, 4)  # add noise so the model
        for row in X                                # learns a smoothed
    ])                                               # approximation, not
    y = np.clip(y, 0, 100)                          # a lookup table
    return X, y


class AssetHealthScorer:
    """Trains once (cheap: a small RandomForest on a few hundred synthetic
    rows) and reuses the fitted model for every score_asset() call."""

    FEATURE_NAMES = [
        "age_days", "checkout_count", "repair_count",
        "warranty_expired", "has_maintenance_record", "low_stock",
    ]

    def __init__(self):
        X, y = generate_synthetic_training_data()
        self.model = RandomForestRegressor(
            n_estimators=250, max_depth=12, min_samples_leaf=2, random_state=42
        )
        self.model.fit(X, y)

    # ---------- Feature extraction ----------

    def _extract_features(self, asset, checkout_count):
        today = date.today()

        # Prefer purchase_date (real acquisition date) for age; fall back to
        # date_added if the operator hasn't recorded one, since it's the
        # only date guaranteed to exist for every asset.
        added = parse_date(asset.purchase_date) or parse_date(asset.date_added)
        age_days = (today - added).days if added else 0
        age_days = max(0, age_days)

        warranty = parse_date(asset.warranty_expiration)
        warranty_expired = 1 if (warranty and warranty < today) else 0

        has_maintenance_record = 1 if asset.last_maintenance_date else 0
        low_stock = 1 if asset.is_low_stock() else 0

        return np.array([[
            age_days,
            checkout_count,
            asset.repair_count or 0,
            warranty_expired,
            has_maintenance_record,
            low_stock,
        ]])

    # ---------- Scoring ----------

    def classify(self, score):
        if score >= HEALTHY_THRESHOLD:
            return "Healthy"
        if score >= MONITOR_THRESHOLD:
            return "Monitor"
        return "Replace Soon"

    def recommend(self, asset, score, status):
        """Rule-based recommendation text. The ML model predicts the
        *score*; the recommendation is a direct, human-readable mapping
        from status (+ a couple of specific risk factors) to an action,
        which keeps the output predictable and explainable rather than
        having a second model generate free-form advice."""
        parts = []
        if status == "Replace Soon":
            parts.append("Replace this asset within the next six months.")
        elif status == "Monitor":
            parts.append("Schedule preventive maintenance and keep an eye on performance.")
        else:
            parts.append("Continue normal operation.")

        warranty = parse_date(asset.warranty_expiration)
        if warranty and warranty < date.today() and status != "Healthy":
            parts.append("Its warranty has expired, so repairs would be out of pocket.")
        if (asset.repair_count or 0) >= 3 and status != "Healthy":
            parts.append(f"It has already been repaired {asset.repair_count} time(s).")

        return " ".join(parts)

    def score_asset(self, asset, checkout_count):
        """Returns (score: int 0-100, status: str, recommendation: str)."""
        features = self._extract_features(asset, checkout_count)
        raw_score = float(self.model.predict(features)[0])
        score = int(round(max(0, min(100, raw_score))))
        status = self.classify(score)
        recommendation = self.recommend(asset, score, status)
        return score, status, recommendation


# Module-level singleton -- training ~400 synthetic rows with a shallow
# RandomForest is fast enough to do once per process at import time.
scorer = AssetHealthScorer()


def recalculate_all(tracker):
    """Score every asset currently in the system and persist the results.

    Returns a list of dicts (one per asset) describing what was computed,
    which app.py uses to flash a short summary to the operator.
    """
    assets = tracker.list_all_assets()
    checkout_counts = tracker.get_checkout_counts()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    results = []
    for asset in assets:
        checkout_count = checkout_counts.get(asset.asset_id, 0)
        score, status, recommendation = scorer.score_asset(asset, checkout_count)
        tracker.db.update_asset_health(asset.asset_id, score, status, recommendation, now_str)
        results.append({
            "asset_id": asset.asset_id,
            "name": asset.name,
            "score": score,
            "status": status,
            "recommendation": recommendation,
        })
    return results
