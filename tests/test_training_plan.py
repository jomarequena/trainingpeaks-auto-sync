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
        self.assertEqual(dates[0], date(2026, 10, 29))
        self.assertIn(date(2026, 11, 3), dates)
        self.assertEqual(dates[-1], date(2027, 4, 4))

    def test_sessions_follow_weekly_schedule_and_race_exceptions(self):
        weeks = defaultdict(list)
        for entry in self.plan:
            session_date = date.fromisoformat(entry["date"])
            monday = session_date - timedelta(days=session_date.weekday())
            weeks[monday].append((session_date, entry))

        race_dates = set()
        for sessions in weeks.values():
            if any(session_date == date(2026, 10, 29) for session_date, _entry in sessions):
                self.assertEqual(len(sessions), 1)
                continue
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

    def test_one_off_caco_structure_smoke_test_is_exactly_20_minutes(self):
        test_workout = next(
            entry for entry in self.plan if entry["date"] == "2026-10-29"
        )
        self.assertEqual(test_workout["title"], "PRUEBA CACO estructurada — 20 min")
        self.assertIn("6 repeticiones de 1 min", test_workout["description"])
        _wire, duration_seconds = auto_sync_tp.build_wire_structure(
            test_workout["structure"]
        )
        self.assertEqual(duration_seconds, 20 * 60)

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
            if entry["sport"] == "Run" and date(2026, 11, 3) <= session_date <= date(2026, 11, 14):
                self.assertIn("CACO", entry["title"])
                self.assertLessEqual(
                    max(step["intensity_max"] for step in entry["structure"]["steps"]),
                    85,
                )

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
                "CACO" in entry["description"] and "trote" in entry["description"]
                for entry in first_week_runs
            )
        )
        second_week_runs = [
            entry
            for _day, entry in weeks[date(2026, 11, 9)]
            if entry["sport"] == "Run"
        ]
        self.assertEqual(len(second_week_runs), 3)
        self.assertTrue(all("CACO" in entry["title"] for entry in second_week_runs))

        run_totals = {
            monday: sum(
                entry["duration_minutes"]
                for _day, entry in sessions
                if entry["sport"] == "Run"
            )
            for monday, sessions in weeks.items()
        }
        self.assertGreater(run_totals[date(2026, 11, 16)], run_totals[date(2026, 11, 2)])
        self.assertGreaterEqual(run_totals[date(2027, 2, 8)], 170)

        long_runs = {
            monday: next(
                entry["duration_minutes"]
                for session_date, entry in sessions
                if entry["sport"] == "Run" and session_date.weekday() == 5
            )
            for monday, sessions in weeks.items()
            if monday < date(2027, 3, 1)
            and any(
                entry["sport"] == "Run" and session_date.weekday() == 5
                for session_date, entry in sessions
            )
        }
        self.assertGreaterEqual(max(long_runs.values()), 90)
        self.assertEqual(max(long_runs.values()), 95)
        self.assertEqual(long_runs[date(2027, 2, 8)], 85)
        self.assertEqual(long_runs[date(2027, 2, 15)], 75)

    def test_running_workout_descriptions_match_duration_and_include_pace_guidance(self):
        races = {"2027-03-07", "2027-04-04"}
        for entry in self.plan:
            if entry["sport"] != "Run" or entry["date"] in races | {"2026-10-29"}:
                continue

            duration = entry["duration_minutes"]
            description = entry["description"]
            self.assertIn(f"= {duration} min.", description, entry["date"])
            if (
                "CACO" not in entry["title"]
                and "progresivos" not in entry["title"]
                and "cuesta" not in entry["title"].lower()
                and "test de ritmo controlado" not in entry["title"].lower()
                and "Sin ritmo objetivo" not in description
            ):
                self.assertRegex(description, r"\d:\d{2}-\d:\d{2} min/km")

    def test_quality_varies_and_target_paces_progress_toward_goal_pace(self):
        workouts_by_week = {}
        for entry in self.plan:
            if entry["sport"] != "Run" or entry["date"] < "2026-11-03":
                continue
            session_date = date.fromisoformat(entry["date"])
            week = (session_date - date(2026, 11, 2)).days // 7 + 1
            workouts_by_week.setdefault(week, []).append(entry)

        quality_titles = [
            next(
                entry["title"]
                for entry in workouts_by_week[week]
                if date.fromisoformat(entry["date"]).weekday() == 1
            )
            for week in (5, 6, 7, 9, 10, 13, 14, 17)
        ]
        self.assertTrue(any("Fartlek" in title for title in quality_titles))
        self.assertTrue(any("cuesta" in title.lower() for title in quality_titles))
        self.assertTrue(any("Tempo" in title for title in quality_titles))

        planned_paces = []
        for week in (5, 6, 9, 10, 13, 14, 17, 20, 21):
            quality_entry = next(
                entry
                for entry in workouts_by_week[week]
                if "min/km" in entry["description"]
                and "Ritmo guía para los tramos vivos" in entry["description"]
            )
            match = re.search(
                r"tramos vivos: (\d+:\d{2})-(\d+:\d{2}) min/km",
                quality_entry["description"],
            )
            self.assertIsNotNone(match, quality_entry["date"])
            planned_paces.append(
                (int(match.group(1).split(":")[0]) * 60 + int(match.group(1).split(":")[1]),
                 int(match.group(2).split(":")[0]) * 60 + int(match.group(2).split(":")[1]))
            )

        self.assertEqual(planned_paces, sorted(planned_paces, reverse=True))
        self.assertIn(
            "4:59-5:05",
            next(
                entry["description"]
                for entry in workouts_by_week[21]
                if "Ritmo guía para los tramos vivos" in entry["description"]
            ),
        )

    def test_intermediate_pace_tests_are_scheduled_before_later_series(self):
        tests = [
            entry for entry in self.plan
            if entry["sport"] == "Run" and entry["title"].startswith("Test de ritmo controlado")
        ]
        self.assertEqual([entry["date"] for entry in tests], ["2027-01-12", "2027-02-09"])
        for entry in tests:
            self.assertIn("20 min", entry["title"])
            self.assertIn("ritmo medio GPS", entry["description"])
            self.assertIn("actualiza el ritmo umbral", entry["description"])
            self.assertEqual(
                sum(step["duration_seconds"] for step in entry["structure"]["steps"]),
                entry["duration_minutes"] * 60,
            )

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
