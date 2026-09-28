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
  - TP_ATHLETE_ID  : tu athlete ID (2018806) — opcional pero recomendado
                     para evitar una llamada extra a la API
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
        r = requests.post(TOKEN_ENDPOINT, headers=headers, timeout=15)
        print(f"DEBUG token exchange: HTTP {r.status_code}")

        if r.status_code == 200:
            data = r.json()
            token = data.get("token") or data.get("access_token") or data.get("accessToken")
            athlete_id = (
                data.get("athleteId")
                or data.get("athlete_id")
                or data.get("userId")
                or data.get("id")
            )
            if token:
                print(f"✅ Token exchange OK. Athlete ID: {athlete_id}")
                return token, athlete_id
            else:
                print(f"DEBUG token response (no token field): {json.dumps(data)[:300]}")
        else:
            print(f"DEBUG token exchange failed body: {r.text[:300]}")

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
        print("❌ Could not determine athlete ID. Add TP_ATHLETE_ID=2018806 as a GitHub secret.")
        sys.exit(1)

    # ── Paso 3: Sincronizar workouts ──────────────────────────────────────
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
