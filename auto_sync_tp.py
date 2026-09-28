"""
auto_sync_tp.py — TrainingPeaks Auto-Sync for GitHub Actions
=============================================================
Flujo de autenticación correcto (extraído del código fuente de tp_mcp):
  1. POST /users/v3/token con Cookie: Production_tpAuth=<valor>
     → devuelve un Bearer token JWT
  2. Usar ese Bearer token en las llamadas a la API fitness/v6

Secrets necesarios en GitHub Actions:
  - TP_AUTH_COOKIE : el VALOR de la cookie Production_tpAuth
                     (solo el valor, no "Production_tpAuth=...")
  - TP_ATHLETE_ID  : tu athlete ID, configurado como secret de GitHub Actions
"""

import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Rutas de archivos
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent
PLAN_FILE = BASE_DIR / "plan_lisboa_2027.json"
SYNC_LOG_FILE = BASE_DIR / "synced_log.json"

# ---------------------------------------------------------------------------
# Constantes de la API de TrainingPeaks (verificadas en código fuente tp_mcp)
# ---------------------------------------------------------------------------
TP_API_BASE = "https://tpapi.trainingpeaks.com"
TOKEN_ENDPOINT = f"{TP_API_BASE}/users/v3/token"

# Mapa de nombres de deporte → workoutTypeValueId de TP
SPORT_TYPE_MAP = {
    "Swim": 1, "swim": 1, "Swimming": 1,
    "Bike": 2, "bike": 2, "Cycling": 2, "Ride": 2,
    "Run": 3, "run": 3, "Running": 3,
    "Walk": 13, "walk": 13,
    "Brick": 4,
    "Crosstrain": 5, "CrossTrain": 5,
    "Race": 6,
    "DayOff": 7, "Day Off": 7, "Rest": 7,
    "Strength": 9,
    "MTB": 8, "Mountain Bike": 8,
    "Other": 100,
}

_BASE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Origin": "https://app.trainingpeaks.com",
    "Referer": "https://app.trainingpeaks.com/",
}


# ---------------------------------------------------------------------------
# Autenticación: cookie → Bearer token
# ---------------------------------------------------------------------------

def get_bearer_token(tp_auth_cookie_value: str) -> tuple[str | None, int | None]:
    """
    Intercambia la cookie Production_tpAuth por un Bearer token JWT.

    Args:
        tp_auth_cookie_value: El VALOR de la cookie Production_tpAuth
                              (lo que guardas en el secret TP_AUTH_COOKIE).

    Returns:
        (access_token, athlete_id) o (None, None) si falla.
    """
    headers = {
        **_BASE_HEADERS,
        "Cookie": f"Production_tpAuth={tp_auth_cookie_value.strip()}",
    }

    try:
        # El endpoint /users/v3/token acepta GET (no POST)
        r = requests.get(TOKEN_ENDPOINT, headers=headers, timeout=15)
        print(f"DEBUG token exchange: HTTP {r.status_code}")

        if r.status_code == 200:
            data = r.json()
            # Respuesta real: {"success": true, "token": {"access_token": "...", ...}}
            token_obj = data.get("token") or {}
            if isinstance(token_obj, str):
                # por si acaso devuelve el token directamente como string
                access_token = token_obj
            else:
                access_token = (
                    token_obj.get("access_token")
                    or data.get("access_token")
                    or data.get("accessToken")
                )
            # El athlete_id no viene en el token; se usa env var o hardcode
            athlete_id = (
                data.get("athleteId")
                or data.get("athlete_id")
                or token_obj.get("athleteId")
            )
            if access_token:
                print(f"✅ Token exchange OK! Expires in: {token_obj.get('expires_in', '?')}s")
                return access_token, athlete_id
            else:
                print(f"DEBUG token response keys: {list(data.keys())}")
                print(f"DEBUG token_obj keys: {list(token_obj.keys()) if isinstance(token_obj, dict) else token_obj}")
        else:
            print(f"DEBUG token exchange failed: HTTP {r.status_code} — {r.text[:300]}")

    except Exception as e:
        print(f"DEBUG token exchange exception: {e}")

    return None, None


def get_api_headers(bearer_token: str) -> dict:
    """Cabeceras con Bearer token para llamadas a la API."""
    return {
        **_BASE_HEADERS,
        "Authorization": f"Bearer {bearer_token}",
        "Content-Type": "application/json",
    }


# ---------------------------------------------------------------------------
# Crear workout
# ---------------------------------------------------------------------------

def create_workout(
    bearer_token: str,
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
    sport_id = SPORT_TYPE_MAP.get(sport, 100)

    payload: dict = {
        "athleteId": athlete_id,
        "workoutDay": f"{date_str}T00:00:00",
        "workoutTypeValueId": sport_id,
        "title": title,
        "description": description or "",
        "startTimePlanned": None,
    }

    if duration_minutes is not None:
        payload["totalTimePlanned"] = int(duration_minutes * 60)  # en segundos

    if tss_planned is not None:
        payload["tssPlanned"] = float(tss_planned)

    url = f"{TP_API_BASE}/fitness/v6/athletes/{athlete_id}/workouts"

    try:
        r = requests.post(
            url,
            headers=get_api_headers(bearer_token),
            json=payload,
            timeout=20,
        )
        print(f"DEBUG create_workout: HTTP {r.status_code}")

        if r.status_code in (200, 201):
            data = r.json()
            workout_id = data.get("id") or data.get("workoutId")
            return {"success": True, "workout_id": workout_id, "message": "OK"}
        else:
            msg = r.text[:400]
            print(f"DEBUG response body: {msg}")
            return {
                "success": False,
                "workout_id": None,
                "message": f"HTTP {r.status_code}: {msg}",
            }
    except Exception as e:
        return {"success": False, "workout_id": None, "message": str(e)}


def get_workouts_for_date(bearer_token: str, athlete_id: int, date_str: str) -> dict:
    """List all workouts on a date; an unverified response must never permit creation."""
    url = (
        f"{TP_API_BASE}/fitness/v6/athletes/{athlete_id}/workouts/"
        f"{date_str}/{date_str}"
    )

    try:
        response = requests.get(
            url,
            headers=get_api_headers(bearer_token),
            timeout=20,
        )
    except requests.RequestException as e:
        return {"success": False, "workouts": [], "message": str(e)}

    if response.status_code != 200:
        return {
            "success": False,
            "workouts": [],
            "message": f"HTTP {response.status_code}: {response.text[:400]}",
        }

    try:
        workouts = response.json()
    except ValueError as e:
        return {"success": False, "workouts": [], "message": f"Invalid JSON response: {e}"}

    if not isinstance(workouts, list):
        return {
            "success": False,
            "workouts": [],
            "message": "Expected a list of workouts in the API response.",
        }

    return {"success": True, "workouts": workouts, "message": "OK"}


def normalize_workout_date(value: object) -> str | None:
    """Normalize ISO date or datetime strings to the workout's calendar date."""
    if not isinstance(value, str):
        return None

    value = value.strip()
    try:
        if len(value) == 10:
            return date.fromisoformat(value).isoformat()
        if len(value) > 10 and value[10] in ("T", " "):
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return None
    return None


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

    tp_auth_cookie = os.environ.get("TP_AUTH_COOKIE", "").strip()

    print("=" * 50)
    print(f"--- TP GitHub Actions Sync [{datetime.now().isoformat()}] ---")
    print(f"Target Dates (2-day window): {target_dates}")
    print(f"DEBUG: TP_AUTH_COOKIE present: {bool(tp_auth_cookie)}, length: {len(tp_auth_cookie)}")
    print("=" * 50)

    if not tp_auth_cookie:
        print("❌ TP_AUTH_COOKIE is empty. Add it as a GitHub Actions secret.")
        sys.exit(1)

    # ── Paso 1: Obtener Bearer token ──────────────────────────────────────
    bearer_token, api_athlete_id = get_bearer_token(tp_auth_cookie)

    if not bearer_token:
        print("❌ Could not get Bearer token. Check your TP_AUTH_COOKIE value.")
        print("   Asegúrate de que el secret contiene solo el VALOR de Production_tpAuth,")
        print("   no la string completa 'Production_tpAuth=...'")
        sys.exit(1)

    # ── Paso 2: Resolver athlete ID ───────────────────────────────────────
    athlete_id_env = os.environ.get("TP_ATHLETE_ID", "").strip()
    if athlete_id_env:
        athlete_id = int(athlete_id_env)
        print(f"✅ Athlete ID from env var: {athlete_id}")
    elif api_athlete_id:
        athlete_id = int(api_athlete_id)
        print(f"✅ Athlete ID from token response: {athlete_id}")
    else:
        print("❌ Could not determine athlete ID. Add your athlete ID as the TP_ATHLETE_ID GitHub Actions secret.")
        sys.exit(1)

    # ── Paso 3: Sincronizar workouts ──────────────────────────────────────
    plan = load_plan()
    sync_log = load_sync_log()
    errors = 0

    for item in plan:
        item_date = normalize_workout_date(item.get("date", ""))
        if item_date not in target_dates:
            continue

        if item_date in sync_log:
            if sync_log[item_date].get("status") == "skipped_existing":
                print(f"ℹ️  Already skipped for {item_date}: workout already exists")
            else:
                print(f"ℹ️  Already synced for {item_date}: {sync_log[item_date]['title']}")
            continue

        title = item.get("title", "Workout")
        sport = item.get("sport", "Other")

        existing = get_workouts_for_date(bearer_token, athlete_id, item_date)
        if not existing["success"]:
            print(f"❌ ERROR checking workouts for {item_date}: {existing['message']}")
            errors += 1
            continue

        if existing["workouts"]:
            existing_workout = existing["workouts"][0]
            existing_workout_id = None
            if isinstance(existing_workout, dict):
                existing_workout_id = (
                    existing_workout.get("workoutId") or existing_workout.get("id")
                )
            print(f"ℹ️  Skipping {item_date}: {len(existing['workouts'])} workout(s) already exist")
            sync_log[item_date] = {
                "status": "skipped_existing",
                "title": title,
                "sport": sport,
                "existing_workout_id": (
                    str(existing_workout_id) if existing_workout_id is not None else None
                ),
                "skipped_at": datetime.now().isoformat(),
            }
            save_sync_log(sync_log)
            continue

        print(f"🚀 Uploading workout for {item_date}: {title} ({sport})...")

        res = create_workout(
            bearer_token=bearer_token,
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
