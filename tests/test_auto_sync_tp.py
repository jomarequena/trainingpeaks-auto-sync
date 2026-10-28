import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime as RealDateTime
from pathlib import Path
from unittest.mock import patch

import requests

import auto_sync_tp


class FixedDateTime:
    @staticmethod
    def now():
        return RealDateTime(2030, 1, 1, 10, 0, 0)

    @staticmethod
    def fromisoformat(value):
        return RealDateTime.fromisoformat(value)


class WorkoutLookupTests(unittest.TestCase):
    @patch("auto_sync_tp.get_api_headers", return_value={"Authorization": "Bearer test"})
    @patch("auto_sync_tp.requests.get")
    def test_uses_date_range_endpoint_and_returns_all_entries(self, get, _headers):
        response = get.return_value
        response.status_code = 200
        response.json.return_value = [{"workoutId": 12, "completed": True}]

        result = auto_sync_tp.get_workouts_for_date("token", 42, "2030-01-01")

        self.assertTrue(result["success"])
        self.assertEqual(result["workouts"], [{"workoutId": 12, "completed": True}])
        self.assertEqual(
            get.call_args.args[0],
            "https://tpapi.trainingpeaks.com/fitness/v6/athletes/42/"
            "workouts/2030-01-01/2030-01-01",
        )

    @patch("auto_sync_tp.requests.get", side_effect=requests.ConnectionError("offline"))
    def test_network_error_fails_closed(self, _get):
        result = auto_sync_tp.get_workouts_for_date("token", 42, "2030-01-01")

        self.assertFalse(result["success"])
        self.assertIn("offline", result["message"])

    @patch("auto_sync_tp.requests.get")
    def test_non_success_status_and_invalid_payload_fail_closed(self, get):
        response = get.return_value
        response.status_code = 503
        response.text = "unavailable"
        result = auto_sync_tp.get_workouts_for_date("token", 42, "2030-01-01")
        self.assertFalse(result["success"])
        self.assertIn("503", result["message"])

        response.status_code = 200
        response.json.return_value = {"workouts": []}
        result = auto_sync_tp.get_workouts_for_date("token", 42, "2030-01-01")
        self.assertFalse(result["success"])
        self.assertIn("Expected a list", result["message"])

        response.json.side_effect = ValueError("malformed JSON")
        result = auto_sync_tp.get_workouts_for_date("token", 42, "2030-01-01")
        self.assertFalse(result["success"])
        self.assertIn("Invalid JSON", result["message"])

    def test_normalizes_date_and_datetime_values(self):
        self.assertEqual(
            auto_sync_tp.normalize_workout_date("2030-01-01T00:00:00Z"),
            "2030-01-01",
        )
        self.assertEqual(
            auto_sync_tp.normalize_workout_date("2030-01-01"),
            "2030-01-01",
        )
        self.assertIsNone(auto_sync_tp.normalize_workout_date("not-a-date"))


class StructuredWorkoutCreationTests(unittest.TestCase):
    @patch("auto_sync_tp.get_api_headers", return_value={"Authorization": "token"})
    @patch("auto_sync_tp.requests.post")
    def test_planned_duration_uses_hours_for_future_session_lengths(self, post, _headers):
        response = post.return_value
        response.status_code = 201
        response.json.return_value = {"workoutId": 789}

        result = auto_sync_tp.create_workout(
            bearer_token="token",
            athlete_id=42,
            date_str="2030-01-02",
            sport="Run",
            title="Long run",
            duration_minutes=75,
        )

        self.assertTrue(result["success"])
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["totalTimePlanned"], 1.25)

    @patch("auto_sync_tp.get_api_headers", return_value={"Authorization": "token"})
    @patch("auto_sync_tp.requests.post")
    def test_posts_wire_structure_and_matching_planned_duration(self, post, _headers):
        response = post.return_value
        response.status_code = 201
        response.json.return_value = {"workoutId": 456}
        structure = {
            "primaryIntensityMetric": "percentOfThresholdPace",
            "steps": [
                {
                    "name": "Warm up",
                    "duration_seconds": 300,
                    "intensity_min": 40,
                    "intensity_max": 55,
                    "intensityClass": "warmUp",
                },
                {
                    "name": "Easy run",
                    "duration_seconds": 600,
                    "intensity_min": 70,
                    "intensity_max": 85,
                },
                {
                    "name": "Cool down",
                    "duration_seconds": 300,
                    "intensity_min": 40,
                    "intensity_max": 55,
                    "intensityClass": "coolDown",
                },
            ],
        }

        result = auto_sync_tp.create_workout(
            bearer_token="token",
            athlete_id=42,
            date_str="2030-01-01",
            sport="Run",
            title="Structured easy run",
            duration_minutes=20,
            structure=structure,
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["workout_id"], 456)
        payload = post.call_args.kwargs["json"]
        wire = json.loads(payload["structure"])
        self.assertAlmostEqual(payload["totalTimePlanned"], 20 / 60)
        self.assertEqual(wire["primaryIntensityMetric"], "percentOfThresholdPace")
        self.assertEqual([block["begin"] for block in wire["structure"]], [0, 300, 900])
        self.assertEqual([block["end"] for block in wire["structure"]], [300, 900, 1200])

    @patch("auto_sync_tp.requests.post")
    def test_rejects_duration_mismatch_before_api_call(self, post):
        result = auto_sync_tp.create_workout(
            bearer_token="token",
            athlete_id=42,
            date_str="2030-01-01",
            sport="Run",
            title="Mismatched workout",
            duration_minutes=20,
            structure={
                "primaryIntensityMetric": "percentOfThresholdPace",
                "steps": [
                    {
                        "name": "Easy run",
                        "duration_seconds": 600,
                        "intensity_min": 70,
                        "intensity_max": 85,
                    }
                ],
            },
        )

        self.assertFalse(result["success"])
        self.assertIn("does not match duration_minutes", result["message"])
        post.assert_not_called()


class SyncDuplicatePreventionTests(unittest.TestCase):
    def _run_sync(self, plan_date="2030-01-01T00:00:00", log=None):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        plan_file = Path(temp_dir.name) / "plan.json"
        log_file = Path(temp_dir.name) / "synced_log.json"
        plan_file.write_text(
            json.dumps([{"date": plan_date, "title": "Easy run", "sport": "Run"}]),
            encoding="utf-8",
        )
        if log is not None:
            log_file.write_text(json.dumps(log), encoding="utf-8")

        with (
            patch.object(auto_sync_tp, "PLAN_FILE", plan_file),
            patch.object(auto_sync_tp, "SYNC_LOG_FILE", log_file),
            patch.object(auto_sync_tp, "datetime", FixedDateTime),
            patch.object(auto_sync_tp, "get_bearer_token", return_value=("token", None)),
            patch.dict(os.environ, {"TP_AUTH_COOKIE": "cookie", "TP_ATHLETE_ID": "42"}),
            redirect_stdout(io.StringIO()),
        ):
            code = 0
            try:
                auto_sync_tp.sync()
            except SystemExit as exc:
                code = exc.code

        saved_log = json.loads(log_file.read_text(encoding="utf-8")) if log_file.exists() else {}
        return code, saved_log

    @patch("auto_sync_tp.create_workout")
    @patch("auto_sync_tp.get_workouts_for_date")
    def test_existing_workout_is_logged_as_skipped(self, lookup, create):
        lookup.return_value = {
            "success": True,
            "workouts": [{"workoutId": 123, "completed": True}],
        }

        code, sync_log = self._run_sync()

        self.assertEqual(code, 0)
        create.assert_not_called()
        self.assertEqual(sync_log["2030-01-01"]["status"], "skipped_existing")
        self.assertEqual(sync_log["2030-01-01"]["existing_workout_id"], "123")

    @patch("auto_sync_tp.create_workout")
    @patch("auto_sync_tp.get_workouts_for_date")
    def test_lookup_failure_exits_nonzero_without_creation(self, lookup, create):
        lookup.return_value = {
            "success": False,
            "workouts": [],
            "message": "API unavailable",
        }

        code, sync_log = self._run_sync()

        self.assertEqual(code, 1)
        create.assert_not_called()
        self.assertNotIn("2030-01-01", sync_log)

    @patch("auto_sync_tp.create_workout")
    @patch("auto_sync_tp.get_workouts_for_date")
    def test_empty_list_allows_creation(self, lookup, create):
        lookup.return_value = {"success": True, "workouts": [], "message": "OK"}
        create.return_value = {"success": True, "workout_id": 456, "message": "OK"}

        code, sync_log = self._run_sync()

        self.assertEqual(code, 0)
        create.assert_called_once()
        self.assertEqual(sync_log["2030-01-01"]["workout_id"], "456")
        self.assertNotIn("status", sync_log["2030-01-01"])

    @patch("auto_sync_tp.create_workout")
    @patch("auto_sync_tp.get_workouts_for_date")
    def test_skipped_entry_prevents_rechecking_on_later_run(self, lookup, create):
        existing_log = {
            "2030-01-01": {
                "status": "skipped_existing",
                "title": "Easy run",
                "sport": "Run",
            }
        }

        code, _sync_log = self._run_sync(log=existing_log)

        self.assertEqual(code, 0)
        lookup.assert_not_called()
        create.assert_not_called()


if __name__ == "__main__":
    unittest.main()
