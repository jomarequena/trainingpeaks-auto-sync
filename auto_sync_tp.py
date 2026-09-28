import asyncio
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add src to path if tp_mcp exists locally
BASE_DIR = Path(__file__).parent
PLAN_FILE = BASE_DIR / "plan_lisboa_2027.json"
SYNC_LOG_FILE = BASE_DIR / "synced_log.json"

# Import tp_mcp if installed or local
try:
    from tp_mcp.tools.workouts import tp_create_workout
except ImportError:
    # If tp_mcp is installed via pip/requirements
    from tp_mcp.tools.workouts import tp_create_workout

def load_plan():
    if not PLAN_FILE.exists():
        print(f"Plan file {PLAN_FILE} not found!")
        return []
    with open(PLAN_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def load_sync_log():
    if SYNC_LOG_FILE.exists():
        with open(SYNC_LOG_FILE, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except Exception:
                return {}
    return {}

def save_sync_log(log_data):
    with open(SYNC_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(log_data, f, indent=2, ensure_ascii=False)

async def sync():
    today = datetime.now().date()
    target_dates = [
        today.strftime("%Y-%m-%d"),
        (today + timedelta(days=1)).strftime("%Y-%m-%d")
    ]
    
    plan = load_plan()
    sync_log = load_sync_log()

    cookie_val = os.environ.get("TP_AUTH_COOKIE", "")
    print(f"==================================================")
    print(f"--- TP GitHub Actions Sync [{datetime.now().isoformat()}] ---")
    print(f"Target Dates (2-day window): {target_dates}")
    print(f"DEBUG: TP_AUTH_COOKIE present: {bool(cookie_val)}, length: {len(cookie_val)}")
    print(f"==================================================")

    for item in plan:
        item_date = item["date"]
        if item_date in target_dates:
            if item_date in sync_log:
                print(f"ℹ️ Already synced for {item_date}: {sync_log[item_date]['title']}")
                continue
            
            print(f"🚀 Uploading workout for {item_date}: {item['title']} ({item['sport']})...")
            res = await tp_create_workout(
                date_str=item_date,
                sport=item["sport"],
                title=item["title"],
                duration_minutes=item.get("duration_minutes"),
                tss_planned=item.get("tss"),
                description=item.get("description")
            )
            
            if res.get("success"):
                workout_id = str(res.get("workout_id"))
                print(f"✅ SUCCESS! Created workout ID {workout_id} for {item_date}")
                sync_log[item_date] = {
                    "workout_id": workout_id,
                    "title": item["title"],
                    "sport": item["sport"],
                    "synced_at": datetime.now().isoformat()
                }
                save_sync_log(sync_log)
            else:
                print(f"❌ ERROR uploading for {item_date}: {res.get('message', res)}")

if __name__ == "__main__":
    asyncio.run(sync())
