"""
app.py
Flask web front-end for the Asset Tracking System.

Reuses the existing tracker.py / database.py / models.py / reports.py
layer untouched -- this file is the "swap the CLI for a web UI" step
the README calls out. Run with:

    python3 app.py

Then visit http://130.0.0.1:5000
"""

from flask import Flask, render_template, request, redirect, url_for, flash, Response

from tracker import AssetTracker
from reports import build_usage_report, export_report

app = Flask(__name__)
app.secret_key = "asset-tracker-dev-key"  # fine for a local/portfolio demo

tracker = AssetTracker()


@app.route("/")
def dashboard():
    assets = tracker.list_all_assets()
    low_stock = tracker.get_low_stock_alerts()
    checked_out = [a for a in assets if a.status == "Checked Out"]

    stats = {
        "total": len(assets),
        "available": len(assets) - len(checked_out),
        "checked_out": len(checked_out),
        "low_stock": len(low_stock),
    }

    return render_template(
        "index.html",
        assets=assets,
        low_stock=low_stock,
        stats=stats,
    )


@app.route("/add", methods=["GET", "POST"])
def add_equipment():
    if request.method == "POST":
        asset_id = request.form.get("asset_id", "")
        name = request.form.get("name", "")
        category = request.form.get("category", "")
        quantity = request.form.get("quantity", "1")
        threshold = request.form.get("threshold", "1")

        try:
            quantity = int(quantity)
            threshold = int(threshold)
        except ValueError:
            flash("Quantity and threshold must be whole numbers.", "error")
            return render_template("add.html", form=request.form)

        ok, msg = tracker.add_equipment(asset_id, name, category, quantity, threshold)
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


if __name__ == "__main__":
    app.run(debug=True)
