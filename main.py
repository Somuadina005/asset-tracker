"""
main.py
Command-line interface for the Asset Tracking System.

Run with:  python3 main.py
"""

from tracker import AssetTracker
from reports import build_usage_report, export_report


MENU = """
==================================================
        ASSET TRACKING SYSTEM
==================================================
 1. Add new equipment
 2. Check out equipment
 3. Check in equipment
 4. Search by Asset ID
 5. Search by name (keyword)
 6. View low-stock alerts
 7. List all equipment
 8. Generate usage report
 9. View history for an asset
 0. Exit
==================================================
"""


def prompt_int(prompt, default=None):
    raw = input(prompt).strip()
    if raw == "" and default is not None:
        return default
    try:
        return int(raw)
    except ValueError:
        print("  Please enter a whole number.")
        return prompt_int(prompt, default)


def add_equipment_flow(tracker):
    print("\n-- Add New Equipment --")
    asset_id = input("Asset ID (e.g. LT-001): ").strip()
    name = input("Name (e.g. Dell Latitude Laptop): ").strip()
    category = input("Category (e.g. Electronics, Medical, Vehicle): ").strip()
    quantity = prompt_int("Quantity on hand [1]: ", default=1)
    threshold = prompt_int("Low-stock threshold [1]: ", default=1)

    ok, msg = tracker.add_equipment(asset_id, name, category, quantity, threshold)
    print(f"\n{'✔' if ok else '✘'} {msg}")


def check_out_flow(tracker):
    print("\n-- Check Out Equipment --")
    asset_id = input("Asset ID: ").strip()
    holder = input("Checking out to (name): ").strip()
    ok, msg = tracker.check_out(asset_id, holder)
    print(f"\n{'✔' if ok else '✘'} {msg}")


def check_in_flow(tracker):
    print("\n-- Check In Equipment --")
    asset_id = input("Asset ID: ").strip()
    ok, msg = tracker.check_in(asset_id)
    print(f"\n{'✔' if ok else '✘'} {msg}")


def search_by_id_flow(tracker):
    print("\n-- Search by Asset ID --")
    asset_id = input("Asset ID: ").strip()
    asset = tracker.search_by_id(asset_id)
    print(f"\n{asset}" if asset else "\nNo asset found with that ID.")


def search_by_name_flow(tracker):
    print("\n-- Search by Name --")
    keyword = input("Keyword: ").strip()
    results = tracker.search_by_name(keyword)
    if not results:
        print("\nNo matching assets found.")
        return
    print(f"\nFound {len(results)} match(es):")
    for a in results:
        print(f"  {a}")


def low_stock_flow(tracker):
    print("\n-- Low Stock Alerts --")
    alerts = tracker.get_low_stock_alerts()
    if not alerts:
        print("All assets are above their low-stock threshold. ✔")
        return
    for a in alerts:
        print(f"  ⚠ {a}")


def list_all_flow(tracker):
    print("\n-- All Equipment --")
    assets = tracker.list_all_assets()
    if not assets:
        print("No equipment on file yet.")
        return
    for a in assets:
        print(f"  {a}")


def report_flow(tracker):
    print("\n" + build_usage_report(tracker))
    save = input("\nSave this report to a text file? (y/n): ").strip().lower()
    if save == "y":
        path = export_report(tracker, "usage_report.txt")
        print(f"Saved to {path}")


def history_flow(tracker):
    print("\n-- Asset History --")
    asset_id = input("Asset ID: ").strip()
    logs = tracker.get_logs_for_asset(asset_id)
    if not logs:
        print("No history found for that asset.")
        return
    for log in logs:
        print(f"  {log}")


def main():
    tracker = AssetTracker()
    print("Welcome to the Asset Tracking System.")

    actions = {
        "1": add_equipment_flow,
        "2": check_out_flow,
        "3": check_in_flow,
        "4": search_by_id_flow,
        "5": search_by_name_flow,
        "6": low_stock_flow,
        "7": list_all_flow,
        "8": report_flow,
        "9": history_flow,
    }

    try:
        while True:
            print(MENU)
            choice = input("Choose an option: ").strip()
            if choice == "0":
                print("\nGoodbye!")
                break
            action = actions.get(choice)
            if action:
                action(tracker)
            else:
                print("\nInvalid option, try again.")
    finally:
        tracker.close()


if __name__ == "__main__":
    main()
