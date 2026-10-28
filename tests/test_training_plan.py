import json
import unittest
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path


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
            self.assertEqual(set(entry), expected_keys)
            dates.append(date.fromisoformat(entry["date"]))
            self.assertIn(entry["sport"], {"Run", "Bike"})
            self.assertIsInstance(entry["duration_minutes"], int)
            self.assertGreater(entry["duration_minutes"], 0)
            self.assertIsInstance(entry["tss"], (int, float))
            self.assertIsInstance(entry["description"], str)
            self.assertTrue(entry["description"])

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
        self.assertIn("no competición", preparation_race["description"].lower())
        self.assertIn("no correr a tope", preparation_race["description"].lower())
        self.assertIn("1h45 aspiracional", target_race["title"].lower())
        self.assertIn("no garantizada", target_race["description"].lower())

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


if __name__ == "__main__":
    unittest.main()
