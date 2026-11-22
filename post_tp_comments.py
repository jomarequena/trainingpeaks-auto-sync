#!/usr/bin/env python3
"""Publica en TrainingPeaks los comentarios pendientes de comments/.

Cada archivo comments/YYYY-MM-DD_<run|bike>.txt es el informe del entreno de ese
día (lo genera la tarea "Informe del entreno de ayer" en el Mac). Este script,
lanzado por GitHub Actions con los secrets TP_AUTH_COOKIE y TP_ATHLETE_ID,
lo publica como comentario del workout de ese día y lo apunta en
comments/posted.json para no repetirlo.
"""
import json
import os
import re
import sys
from pathlib import Path

import requests

API = "https://tpapi.trainingpeaks.com"
BASE_DIR = Path(__file__).parent
COMMENTS_DIR = BASE_DIR / "comments"
POSTED_FILE = COMMENTS_DIR / "posted.json"
NAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_(run|bike)\.txt$")
SPORT_IDS = {"run": {3}, "bike": {2, 8}}
BASE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Origin": "https://app.trainingpeaks.com",
    "Referer": "https://app.trainingpeaks.com/",
}


def auth():
    cookie = os.environ.get("TP_AUTH_COOKIE", "").strip()
    if not cookie:
        sys.exit("Falta el secret TP_AUTH_COOKIE")
    r = requests.get(f"{API}/users/v3/token", timeout=15,
                     headers={**BASE_HEADERS, "Cookie": f"Production_tpAuth={cookie}"})
    tok = (r.json().get("token") or {}) if r.status_code == 200 else {}
    access = tok.get("access_token") if isinstance(tok, dict) else tok
    if not access:
        sys.exit(f"Cookie de TrainingPeaks caducada o inválida (HTTP {r.status_code}). Renueva TP_AUTH_COOKIE.")
    h = {**BASE_HEADERS, "Authorization": f"Bearer {access}", "Content-Type": "application/json"}
    athlete_id = os.environ.get("TP_ATHLETE_ID", "").strip()
    if not athlete_id:
        user = requests.get(f"{API}/users/v3/user", headers=h, timeout=15).json()
        user = user.get("user", user)
        athletes = user.get("athletes") or []
        athlete_id = athletes[0].get("athleteId") if athletes else user.get("personId")
    if not athlete_id:
        sys.exit("No se pudo obtener el athlete ID")
    return h, athlete_id


def post_one(h, athlete_id, day, sport, text):
    r = requests.get(f"{API}/fitness/v6/athletes/{athlete_id}/workouts/{day}/{day}", headers=h, timeout=15)
    if r.status_code != 200:
        return None, f"no se pudieron leer los workouts (HTTP {r.status_code})"
    cands = [w for w in r.json() if w.get("workoutTypeValueId") in SPORT_IDS[sport]]
    if not cands:
        return None, f"no hay workout de {sport} el {day} (se reintentará)"
    cands.sort(key=lambda w: (w.get("totalTime") is None, w.get("workoutId")))
    w = cands[0]
    wid = w["workoutId"]

    full = requests.get(f"{API}/fitness/v6/athletes/{athlete_id}/workouts/{wid}", headers=h, timeout=15)
    comments = (full.json().get("workoutComments") or []) if full.status_code == 200 else []
    first = text.splitlines()[0].strip()
    if any(str(c.get("comment") or c.get("value") or "").strip().startswith(first) for c in comments):
        return {"workout_id": wid, "title": w.get("title"), "note": "ya existía"}, None

    r = requests.post(f"{API}/fitness/v2/athletes/{athlete_id}/workouts/{wid}/comments",
                      headers=h, json={"value": text}, timeout=15)
    if r.status_code not in (200, 201, 204):
        return None, f"TrainingPeaks rechazó el comentario (HTTP {r.status_code}): {r.text[:200]}"
    return {"workout_id": wid, "title": w.get("title")}, None


def main():
    posted = json.loads(POSTED_FILE.read_text()) if POSTED_FILE.exists() else {}
    pending = sorted(p for p in COMMENTS_DIR.glob("*.txt") if NAME_RE.match(p.name) and p.name not in posted)
    if not pending:
        print("Nada pendiente.")
        return
    h, athlete_id = auth()
    errors = []
    for p in pending:
        day, sport = NAME_RE.match(p.name).groups()
        text = p.read_text(encoding="utf-8").strip()
        if not text:
            continue
        ok, err = post_one(h, athlete_id, day, sport, text)
        if ok:
            posted[p.name] = ok
            print(f"OK {p.name} -> workout {ok['workout_id']} ({ok.get('title')}) {ok.get('note', '')}")
        else:
            errors.append(f"{p.name}: {err}")
            print(f"ERROR {p.name}: {err}")
    POSTED_FILE.write_text(json.dumps(posted, ensure_ascii=False, indent=2) + "\n")
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
