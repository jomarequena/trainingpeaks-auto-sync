"""
auto_sync_tp.py — TrainingPeaks Auto-Sync for GitHub Actions
=============================================================
Llama directamente a la API de TrainingPeaks usando la cookie de sesión
del browser (TP_AUTH_COOKIE), sin depender de tp_mcp como librería Python.

Secrets necesarios en GitHub Actions:
  - TP_AUTH_COOKIE  : cookie completa copiada del navegador (campo Cookie:)
  - TP_ATHLETE_ID   : tu athlete ID (2018806) — opcional, se obtiene de la API si no se pone
"""

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Rutas de archivos
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent
PLAN_FILE = BASE_DIR / "plan_lisboa_2027.json"
SYNC_LOG_FILE = BASE_DIR / "synced_log.json"

# ---------------------------------------------------------------------------
# API de TrainingPeaks
# ---------------------------------------------------------------------------
TP_API_BASE = "https://tpapi.trainingpeaks.com"

# Mapa de nombres de deporte (plan JSON) → workoutTypeValueId de TP
SPORT_TYPE_MAP = {
    # Natación
    "Swim": 1, "swim": 1, "Swimming": 1,
    # Bicicleta
    "Bike": 2, "bike": 2, "Cycling": 2, "Ride": 2,
    # Carrera
    "Run": 3, "run": 3, "Running": 3,
    # Otros
    "Walk": 13, "walk": 13,
    "Brick": 4,
    "Crosstrain": 5, "CrossTrain": 5,
    "Race": 6,
    "DayOff": 7, "Day Off": 7, "Rest": 7,
    "Strength": 9,
    "MTB": 8, "Mountain Bike": 8,
    "Other": 100,
}


def build_headers(cookie: str) -> dict:
    """Cabeceras HTTP para la API de TrainingPeaks."""
    return {
        "Cookie": cookie,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (GitHub-Actions-AutoSync/1.0)",
        "Origin": "https://app.trainingpeaks.com",
        "Referer": "https://app.trainingpeaks.com/",
    }


def get_athlete_id(cookie: str) -> int | None:
    """Obtiene el athlete ID desde el perfil de TP."""
    url = f"{TP_API_BASE}/v6/users/user"
    try:
        r = requests.get(url, headers=build_headers(cookie), timeout=15)
        if r.status_code == 200:
            data = r.json()
            # El ID puede venir en distintos campos según la versión de la API
            return (
                data.get("id")
                or data.get("athleteId")
                or data.get("userId")
            )
        else:
            print(f"DEBUG get_athlete_id: HTTP {r.status_code} — {r.text[:200]}")
    except Exception as e:
        print(f"DEBUG get_athlete_id exception: {e}")
    return None


def create_workout(
    cookie: str,
    athlete_id: int,
    date_str: str,
    sport: str,
    title: str,
    duration_minutes: int | None = None,
    tss_planned: float | None = None,
    description: str | None = None,
) -> dict:
    """
    Crea un workout planificado en TrainingPeaks.

    Retorna dict con keys: success (bool), workout_id (int|None), message (str).
    """
    sport_id = SPORT_TYPE_MAP.get(sport, 100)  # fallback → Other

    payload: dict = {
        "athleteId": athlete_id,
        "workoutDay": f"{date_str}T00:00:00",
        "workoutTypeValueId": sport_id,
        "title": title,
        "description": description or "",
        "startTimePlanned": None,
    }

    if duration_minutes is not None:
        payload["totalTimePlanned"] = int(duration_minutes * 60)  # segundos

    if tss_planned is not None:
        payload["tssPlanned"] = float(tss_planned)

    url = f"{TP_API_BASE}/fitness/v6/athletes/{athlete_id}/workouts"

    try:
        r = requests.post(
            url,
            headers=build_headers(cookie),
            json=payload,
            timeout=20,
        )
        print(f"DEBUG create_workout: HTTP {r.status_code}")
        if r.status_code in (200, 201):
            data = r.json()
            workout_id = data.get("id") or data.get("workoutId")
            return {"success": True, "workout_id": workout_id, "message": "OK"}
        else:
            msg = r.text[:300]
            print(f"DEBUG response body: {msg}")
            return {
                "success": False,
                "workout_id": None,
                "message": f"HTTP {r.status_code}: {msg}",
            }
    except Exception as e:
        return {"success": False, "workout_id": None, "message": str(e)}


# ---------------------------------------------------------------------------
# Helpers de log local
# ---------------------------------------------------------------------------

def load_plan() -> list:
    if not PLAN_FILE.exists():
        print(f"❌ Plan file not found: {PLAN_FILE}")
        return []
    with open(PLAN_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def load_sync_log() -> dict:
    if SYNC_LOG_FILE.exists():
        with open(SYNC_LOG_FILE, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except Exception:
                return {}
    return {}


def save_sync_log(log_data: dict) -> None:
    with open(SYNC_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(log_data, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def sync() -> None:
    today = datetime.now().date()
    target_dates = [
        today.strftime("%Y-%m-%d"),
        (today + timedelta(days=1)).strftime("%Y-%m-%d"),
    ]

    cookie = os.environ.get("TP_AUTH_COOKIE", "").strip()

    print("=" * 50)
    print(f"--- TP GitHub Actions Sync [{datetime.now().isoformat()}] ---")
    print(f"Target Dates (2-day window): {target_dates}")
    print(f"DEBUG: TP_AUTH_COOKIE present: {bool(cookie)}, length: {len(cookie)}")
    print("=" * 50)

    if not cookie:
        print("❌ TP_AUTH_COOKIE is empty. Add it as a GitHub Actions secret.")
        sys.exit(1)

    # Obtener athlete ID (env var tiene prioridad; si no, consultar la API)
    athlete_id_env = os.environ.get("TP_ATHLETE_ID", "").strip()
    if athlete_id_env:
        athlete_id = int(athlete_id_env)
        print(f"✅ Athlete ID from env: {athlete_id}")
    else:
        athlete_id = get_athlete_id(cookie)
        if not athlete_id:
            print("❌ Could not get athlete ID from API. Check your TP_AUTH_COOKIE.")
            sys.exit(1)
        print(f"✅ Athlete ID from API: {athlete_id}")

    plan = load_plan()
    sync_log = load_sync_log()
    errors = 0

    for item in plan:
        item_date = item.get("date", "")
        if item_date not in target_dates:
            continue

        if item_date in sync_log:
            print(f"ℹ️  Already synced for {item_date}: {sync_log[item_date]['title']}")
            continue

        title = item.get("title", "Workout")
        sport = item.get("sport", "Other")
        print(f"🚀 Uploading workout for {item_date}: {title} ({sport})...")

        res = create_workout(
            cookie=cookie,
            athlete_id=athlete_id,
            date_str=item_date,
            sport=sport,
            title=title,
            duration_minutes=item.get("duration_minutes"),
            tss_planned=item.get("tss"),
            description=item.get("description"),
        )

        if res["success"]:
            workout_id = str(res["workout_id"])
            print(f"✅ SUCCESS! Created workout ID {workout_id} for {item_date}")
            sync_log[item_date] = {
                "workout_id": workout_id,
                "title": title,
                "sport": sport,
                "synced_at": datetime.now().isoformat(),
            }
            save_sync_log(sync_log)
        else:
            print(f"❌ ERROR uploading for {item_date}: {res['message']}")
            errors += 1

    if errors:
        sys.exit(1)


if __name__ == "__main__":
    sync()
