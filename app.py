"""
app.py
Flask web front-end for the Asset Tracking System.

Reuses the existing tracker.py / database.py / models.py / reports.py
layer untouched -- this file is the "swap the CLI for a web UI" step
the README calls out. Run with:

    python3 app.py

Then visit http://130.0.0.1:5000
"""

from flask import Flask, render_template, request, redirect, url_for, flash, Response, send_from_directory

from tracker import AssetTracker
from reports import build_usage_report, export_report
import chatbot
import health_score_service

app = Flask(
    __name__,
    template_folder=".",  # all files now live in one flat folder --
    static_folder=None,   # templates sit alongside the .py files instead
)                          # of in templates/ and static/ subfolders
app.secret_key = "asset-tracker-dev-key"  # fine for a local/portfolio demo


@app.route("/static/style.css")
def style_css():
    # Flask's default static route serves *any* file in its static folder --
    # with everything flattened into one directory, that would mean
    # app.py, database.py, and even asset_tracker.db become downloadable
    # over HTTP. So static_folder is disabled above, and only this one
    # file is exposed, explicitly, instead.
    return send_from_directory(".", "style.css", mimetype="text/css")

tracker = AssetTracker()


@app.context_processor
def inject_notification_alerts():
    """Makes open notifications (from notification_service.py's tracking
    table) available to every template, so the popup can show on any
    page -- not just the dashboard."""
    return {"popup_alerts": tracker.get_open_notifications()}


@app.route("/")
def dashboard():
    assets = tracker.list_all_assets()

    # Lazily score any asset that has never been through the health-score
    # model yet (e.g. right after it's added), so the dashboard always
    # shows a score without requiring a manual "Recalculate" click first.
    # A full manual recalculation is still available via /health/recalculate
    # for refreshing scores after checkouts, repairs, etc.
    if any(a.health_score is None for a in assets):
        health_score_service.recalculate_all(tracker)
        assets = tracker.list_all_assets()

    low_stock = tracker.get_low_stock_alerts()
    checked_out = [a for a in assets if a.status == "Checked Out"]
    replace_soon = [a for a in assets if a.health_status == "Replace Soon"]

    stats = {
        "total": len(assets),
        "available": len(assets) - len(checked_out),
        "checked_out": len(checked_out),
        "low_stock": len(low_stock),
        "replace_soon": len(replace_soon),
    }

    return render_template(
        "index.html",
        assets=assets,
        low_stock=low_stock,
        replace_soon=replace_soon,
        stats=stats,
    )


@app.route("/health/recalculate", methods=["POST"])
def recalculate_health():
    """Manually refresh every asset's health score -- useful after logging
    repairs/maintenance or checkouts that should shift the score."""
    results = health_score_service.recalculate_all(tracker)
    flagged = sum(1 for r in results if r["status"] != "Healthy")
    flash(f"Recalculated health scores for {len(results)} asset(s) -- {flagged} need attention.", "success")
    return redirect(request.form.get("next") or url_for("dashboard"))


@app.route("/add", methods=["GET", "POST"])
def add_equipment():
    if request.method == "POST":
        asset_id = request.form.get("asset_id", "")
        name = request.form.get("name", "")
        category = request.form.get("category", "")
        quantity = request.form.get("quantity", "1")
        threshold = request.form.get("threshold", "1")
        # Optional -- feed the health-score model and let the AI copilot
        # answer department/warranty-aware questions. Blank is fine.
        department = request.form.get("department", "").strip() or None
        purchase_date = request.form.get("purchase_date", "").strip() or None
        warranty_expiration = request.form.get("warranty_expiration", "").strip() or None
        last_maintenance_date = request.form.get("last_maintenance_date", "").strip() or None
        repair_count = request.form.get("repair_count", "0")

        try:
            quantity = int(quantity)
            threshold = int(threshold)
            repair_count = int(repair_count) if repair_count else 0
        except ValueError:
            flash("Quantity, threshold, and repair count must be whole numbers.", "error")
            return render_template("add.html", form=request.form)

        ok, msg = tracker.add_equipment(
            asset_id, name, category, quantity, threshold,
            department=department, purchase_date=purchase_date,
            warranty_expiration=warranty_expiration,
            last_maintenance_date=last_maintenance_date, repair_count=repair_count,
        )
        flash(msg, "success" if ok else "error")
        if ok:
            return redirect(url_for("dashboard"))
        return render_template("add.html", form=request.form)

    return render_template("add.html", form={})


@app.route("/asset/<asset_id>")
def asset_detail(asset_id):
    asset = tracker.search_by_id(asset_id)
    if not asset:
        flash(f"No asset found with ID {asset_id}.", "error")
        return redirect(url_for("dashboard"))
    logs = tracker.get_logs_for_asset(asset_id)
    return render_template("asset_detail.html", asset=asset, logs=logs)


@app.route("/checkout/<asset_id>", methods=["POST"])
def check_out(asset_id):
    holder = request.form.get("holder", "").strip()
    if not holder:
        flash("Enter a name to check equipment out to.", "error")
        return redirect(url_for("asset_detail", asset_id=asset_id))
    ok, msg = tracker.check_out(asset_id, holder)
    flash(msg, "success" if ok else "error")
    return redirect(request.form.get("next") or url_for("dashboard"))


@app.route("/checkin/<asset_id>", methods=["POST"])
def check_in(asset_id):
    ok, msg = tracker.check_in(asset_id)
    flash(msg, "success" if ok else "error")
    return redirect(request.form.get("next") or url_for("dashboard"))


@app.route("/search")
def search():
    query = request.args.get("q", "").strip()
    results = []
    if query:
        by_id = tracker.search_by_id(query)
        results = [by_id] if by_id else tracker.search_by_name(query)
    return render_template("search.html", query=query, results=results)


@app.route("/report")
def report():
    report_text = build_usage_report(tracker)
    return render_template("report.html", report_text=report_text)


@app.route("/report/export")
def report_export():
    report_text = build_usage_report(tracker)
    return Response(
        report_text,
        mimetype="text/plain",
        headers={"Content-Disposition": "attachment; filename=usage_report.txt"},
    )


@app.route("/notifications")
def notifications():
    history = tracker.get_notification_history()
    return render_template("notifications.html", history=history)


@app.route("/chatbot", methods=["GET", "POST"])
def chatbot_page():
    answer = None
    question = ""
    if request.method == "POST":
        question = request.form.get("question", "").strip()
        if question:
            answer = chatbot.ask(tracker, question)
    return render_template(
        "chatbot.html",
        question=question,
        answer=answer,
        configured=chatbot.is_configured(),
    )


if __name__ == "__main__":
    app.run(debug=True)
