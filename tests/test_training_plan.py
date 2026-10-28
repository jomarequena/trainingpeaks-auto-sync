import json
import re
import unittest
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

import auto_sync_tp


PLAN_FILE = Path(__file__).parents[1] / "plan_lisboa_2027.json"
RACE_DATES = {date(2027, 3, 7), date(2027, 4, 4)}


class TrainingPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = json.loads(PLAN_FILE.read_text(encoding="utf-8"))

    def test_entries_have_valid_schema_and_sorted_unique_dates(self):
        self.assertIsInstance(self.plan, list)
        expected_keys = {
            "date",
            "sport",
            "title",
            "duration_minutes",
            "tss",
            "description",
        }
        dates = []
        for entry in self.plan:
            expected_entry_keys = set(expected_keys)
            if entry["date"] not in {"2027-03-07", "2027-04-04"}:
                expected_entry_keys.add("structure")
            self.assertEqual(set(entry), expected_entry_keys)
            dates.append(date.fromisoformat(entry["date"]))
            self.assertIn(entry["sport"], {"Run", "Bike"})
            self.assertIsInstance(entry["duration_minutes"], int)
            self.assertGreater(entry["duration_minutes"], 0)
            self.assertIsInstance(entry["tss"], (int, float))
            self.assertIsInstance(entry["description"], str)
            self.assertTrue(entry["description"])
            if "structure" in entry:
                self.assertIsInstance(entry["structure"], dict)

        self.assertEqual(dates, sorted(dates))
        self.assertEqual(len(dates), len(set(dates)))
        self.assertEqual(dates[0], date(2026, 11, 3))
        self.assertEqual(dates[-1], date(2027, 4, 4))

    def test_sessions_follow_weekly_schedule_and_race_exceptions(self):
        weeks = defaultdict(list)
        for entry in self.plan:
            session_date = date.fromisoformat(entry["date"])
            monday = session_date - timedelta(days=session_date.weekday())
            weeks[monday].append((session_date, entry))

        race_dates = set()
        for sessions in weeks.values():
            dates = [session_date for session_date, _entry in sessions]
            sports = Counter(entry["sport"] for _session_date, entry in sessions)
            self.assertEqual(sports, {"Run": 3, "Bike": 1})
            self.assertEqual(len(dates), 4)

            for session_date, entry in sessions:
                weekday = session_date.weekday()
                if entry["sport"] == "Bike":
                    self.assertEqual(weekday, 2)
                elif weekday == 6:
                    race_dates.add(session_date)
                else:
                    self.assertIn(weekday, {1, 3, 5})

        self.assertEqual(race_dates, RACE_DATES)

    def test_preparation_test_and_target_race_are_clearly_identified(self):
        by_date = {date.fromisoformat(entry["date"]): entry for entry in self.plan}
        preparation_race = by_date[date(2027, 3, 7)]
        target_race = by_date[date(2027, 4, 4)]

        self.assertIn("test controlado", preparation_race["title"].lower())
        self.assertIn("duración prevista 150 min", preparation_race["description"].lower())
        self.assertIn("no competición", preparation_race["description"].lower())
        self.assertIn("no correr a tope", preparation_race["description"].lower())
        self.assertIn("1h45 aspiracional", target_race["title"].lower())
        self.assertIn("duración orientativa 105 min", target_race["description"].lower())
        self.assertIn("no garantizada", target_race["description"].lower())
        self.assertIn("4:59 min/km", target_race["description"])

    def test_base_build_deloads_and_tapers_are_reflected(self):
        weeks = defaultdict(list)
        for entry in self.plan:
            session_date = date.fromisoformat(entry["date"])
            monday = session_date - timedelta(days=session_date.weekday())
            weeks[monday].append((session_date, entry))

        run_minutes = {
            monday: sum(
                entry["duration_minutes"]
                for _session_date, entry in sessions
                if entry["sport"] == "Run"
            )
            for monday, sessions in weeks.items()
        }
        for deload_monday in (
            date(2026, 11, 23),
            date(2026, 12, 21),
            date(2027, 1, 18),
            date(2027, 2, 15),
        ):
            previous_monday = deload_monday - timedelta(days=7)
            self.assertLess(run_minutes[deload_monday], run_minutes[previous_monday])

        for entry in self.plan:
            session_date = date.fromisoformat(entry["date"])
            if entry["sport"] == "Run" and session_date < date(2027, 1, 26):
                self.assertNotIn("strides", entry["description"].lower())

        for race_date in RACE_DATES:
            race_monday = race_date - timedelta(days=race_date.weekday())
            prior_week_monday = race_monday - timedelta(days=7)
            race_week_running = sum(
                entry["duration_minutes"]
                for session_date, entry in weeks[race_monday]
                if entry["sport"] == "Run" and session_date != race_date
            )
            prior_week_running = run_minutes[prior_week_monday]
            self.assertLess(race_week_running, prior_week_running)

    def test_run_walk_minutes_build_early_and_long_run_progresses_gradually(self):
        weeks = defaultdict(list)
        for entry in self.plan:
            session_date = date.fromisoformat(entry["date"])
            monday = session_date - timedelta(days=session_date.weekday())
            weeks[monday].append((session_date, entry))

        first_week = weeks[date(2026, 11, 2)]
        first_week_runs = [entry for _day, entry in first_week if entry["sport"] == "Run"]
        self.assertEqual(
            [entry["duration_minutes"] for entry in first_week_runs],
            [20, 20, 25],
        )
        self.assertTrue(
            all(
                "CACO" in entry["description"] and "trote muy fácil" in entry["description"]
                for entry in first_week_runs
            )
        )

        run_totals = {
            monday: sum(
                entry["duration_minutes"]
                for _day, entry in sessions
                if entry["sport"] == "Run"
            )
            for monday, sessions in weeks.items()
        }
        self.assertGreater(run_totals[date(2026, 11, 16)], run_totals[date(2026, 11, 2)])
        self.assertGreaterEqual(run_totals[date(2027, 2, 8)], 180)

        long_runs = {
            monday: next(
                entry["duration_minutes"]
                for session_date, entry in sessions
                if entry["sport"] == "Run" and session_date.weekday() == 5
            )
            for monday, sessions in weeks.items()
            if monday < date(2027, 3, 1)
        }
        self.assertGreaterEqual(max(long_runs.values()), 100)
        self.assertEqual(long_runs[date(2027, 2, 8)], 105)

    def test_running_workout_descriptions_match_duration_and_include_pace_guidance(self):
        races = {"2027-03-07", "2027-04-04"}
        for entry in self.plan:
            if entry["sport"] != "Run" or entry["date"] in races:
                continue

            duration = entry["duration_minutes"]
            description = entry["description"]
            self.assertIn(f"= {duration} min.", description, entry["date"])
            self.assertIn("Ritmo medio orientativo", description, entry["date"])
            self.assertRegex(description, r"\d:\d{2}-\d:\d{2} min/km")

            if "strides" in entry["title"].lower():
                easy_minutes = duration - 29.5
                if easy_minutes.is_integer():
                    easy_text = f"{int(easy_minutes)} min"
                else:
                    easy_text = f"{int(easy_minutes)} min 30 s"
                expected_structure = (
                    f"Estructura exacta: 10 min suaves + {easy_text} aeróbicos + "
                    "6 x 20 s (2 min) + 5 x 90 s recuperación (7 min 30 s) + "
                    f"10 min suaves = {duration} min."
                )
                self.assertIn(expected_structure, description, entry["date"])
                self.assertIn("RPE 6/10, no sprintar", description)
            else:
                main_minutes = duration - 10
                expected_structure = (
                    f"Estructura exacta: 5 min caminando + {main_minutes} min de "
                    f"bloque principal + 5 min caminando = {duration} min."
                )
                self.assertIn(expected_structure, description, entry["date"])

    def test_native_structures_match_each_planned_workout_duration(self):
        races = {"2027-03-07", "2027-04-04"}
        for entry in self.plan:
            if entry["date"] in races:
                self.assertNotIn("structure", entry)
                continue

            wire, total_seconds = auto_sync_tp.build_wire_structure(entry["structure"])
            expected_seconds = entry["duration_minutes"] * 60
            self.assertEqual(total_seconds, expected_seconds, entry["date"])
            self.assertEqual(
                sum(block["end"] - block["begin"] for block in wire["structure"]),
                expected_seconds,
                entry["date"],
            )
            self.assertEqual(wire["primaryLengthMetric"], "duration")
            self.assertEqual(
                wire["primaryIntensityMetric"],
                "percentOfFtp" if entry["sport"] == "Bike" else "percentOfThresholdPace",
            )


if __name__ == "__main__":
    unittest.main()
