import unittest

from backend.app.schemas.instruments import MicrowaveConfigRequest
from backend.app.services.instrument_manager import InstrumentManager


class MicrowaveSweepPointsTests(unittest.TestCase):
    def test_exact_10khz_step_over_1mhz(self):
        result = InstrumentManager.compute_sweep_points(2.87e9, 2.88e9, 10_000.0)
        self.assertEqual(result["sweep_points"], 1001)
        self.assertAlmostEqual(result["actual_step_hz"], 10_000.0, places=6)

    def test_default_window_with_default_step(self):
        request = MicrowaveConfigRequest()
        result = InstrumentManager.compute_sweep_points(
            request.sweep_start_hz,
            request.sweep_stop_hz,
            request.sweep_step_hz,
        )
        # (2.92e9 - 2.82e9) / 10e3 + 1 = 10001
        self.assertEqual(result["sweep_points"], 10001)
        self.assertEqual(request.sweep_step_hz, 10_000.0)

    def test_minimum_two_points(self):
        result = InstrumentManager.compute_sweep_points(1.0e9, 1.0e9 + 10_000.0, 10_000.0)
        self.assertEqual(result["sweep_points"], 2)

    def test_round_non_integer_span_ratio(self):
        # span / step = 1.4 → round → 1 → points = 2
        result = InstrumentManager.compute_sweep_points(0.0, 14_000.0, 10_000.0)
        self.assertEqual(result["sweep_points"], 2)
        self.assertAlmostEqual(result["actual_step_hz"], 14_000.0, places=6)

        # span / step = 1.6 → round → 2 → points = 3
        result = InstrumentManager.compute_sweep_points(0.0, 16_000.0, 10_000.0)
        self.assertEqual(result["sweep_points"], 3)
        self.assertAlmostEqual(result["actual_step_hz"], 8_000.0, places=6)

    def test_rejects_invalid_ranges(self):
        with self.assertRaises(ValueError):
            InstrumentManager.compute_sweep_points(2.9e9, 2.8e9, 10_000.0)
        with self.assertRaises(ValueError):
            InstrumentManager.compute_sweep_points(2.8e9, 2.9e9, 0.0)
        with self.assertRaises(ValueError):
            InstrumentManager.compute_sweep_points(2.8e9, 2.9e9, -1.0)

    def test_rejects_too_many_points(self):
        with self.assertRaises(ValueError) as ctx:
            InstrumentManager.compute_sweep_points(0.0, 1.0e9, 1.0, max_points=100)
        self.assertIn("超过上限", str(ctx.exception))

    def test_normalize_updates_points_on_request(self):
        manager = InstrumentManager()
        request = MicrowaveConfigRequest(
            sweep_start_hz=2.87e9,
            sweep_stop_hz=2.88e9,
            sweep_step_hz=10_000.0,
            sweep_points=2,  # stale; should be recomputed
        )
        normalized = manager._normalize_microwave_sweep(request)
        self.assertEqual(normalized.sweep_points, 1001)

    def test_update_microwave_offline_returns_failure_but_caches(self):
        manager = InstrumentManager()
        request = MicrowaveConfigRequest(
            mode="sweep",
            sweep_start_hz=2.87e9,
            sweep_stop_hz=2.88e9,
            sweep_step_hz=10_000.0,
        )
        result = manager.update_microwave(request)
        self.assertFalse(result["success"])
        self.assertIn("未连接", result["message"])
        self.assertEqual(result["data"]["config"]["sweep_points"], 1001)
        self.assertEqual(result["data"]["config"]["sweep_step_hz"], 10_000.0)
        self.assertEqual(result["data"]["config"]["sweep_run_mode"], "trigger")
        self.assertIn("扫频点数=1001", result["message"])

    def test_default_sweep_run_mode_is_trigger(self):
        request = MicrowaveConfigRequest()
        self.assertEqual(request.sweep_run_mode, "trigger")

    def test_offline_caches_free_run_mode(self):
        manager = InstrumentManager()
        request = MicrowaveConfigRequest(
            mode="sweep",
            sweep_run_mode="free",
            sweep_start_hz=2.87e9,
            sweep_stop_hz=2.88e9,
            sweep_step_hz=10_000.0,
        )
        result = manager.update_microwave(request)
        self.assertFalse(result["success"])
        self.assertEqual(result["data"]["config"]["sweep_run_mode"], "free")
        # Offline apply must not mark free_running (no instrument session).
        self.assertNotEqual(result["data"]["sweep_trigger"]["status"], "free_running")

    def test_trigger_blocked_when_free_running(self):
        manager = InstrumentManager()
        manager.microwave_resource = object()
        manager.microwave_state["connected"] = True
        manager.microwave_state["config"]["mode"] = "sweep"
        manager.microwave_state["config"]["sweep_run_mode"] = "free"
        manager.microwave_state["sweep_trigger"] = {
            "running": True,
            "status": "free_running",
            "started_at": None,
            "elapsed_s": 0.0,
            "estimated_duration_s": 0.0,
            "points": 1001,
            "dwell_ms": 5.0,
            "message": "free",
        }
        result = manager.start_microwave_sweep_trigger()
        self.assertFalse(result["success"])
        self.assertIn("Free", result["message"])

    def test_trigger_blocked_when_config_is_free_mode(self):
        manager = InstrumentManager()
        manager.microwave_resource = object()
        manager.microwave_state["connected"] = True
        manager.microwave_state["config"] = MicrowaveConfigRequest(
            mode="sweep",
            sweep_run_mode="free",
            sweep_start_hz=2.87e9,
            sweep_stop_hz=2.88e9,
            sweep_step_hz=10_000.0,
        ).model_dump()
        result = manager.start_microwave_sweep_trigger()
        self.assertFalse(result["success"])
        self.assertIn("Free", result["message"])

    def test_stop_free_running_without_thread(self):
        manager = InstrumentManager()
        manager.microwave_resource = None
        manager.microwave_state["sweep_trigger"] = {
            "running": True,
            "status": "free_running",
            "started_at": None,
            "elapsed_s": 1.0,
            "estimated_duration_s": 0.0,
            "points": 100,
            "dwell_ms": 5.0,
            "message": "free",
        }
        result = manager.stop_microwave_sweep_trigger()
        self.assertTrue(result["success"])
        self.assertFalse(result["data"]["sweep_trigger"]["running"])
        self.assertEqual(result["data"]["sweep_trigger"]["status"], "cancelled")

    def test_hardware_sweep_duration_estimate(self):
        manager = InstrumentManager()
        estimated = manager._estimate_hardware_sweep_duration_s(1000, 5.0)
        self.assertAlmostEqual(estimated, 1000 * 0.005 + 0.2, places=6)

    def test_trigger_requires_connection(self):
        manager = InstrumentManager()
        result = manager.start_microwave_sweep_trigger()
        self.assertFalse(result["success"])
        self.assertIn("未连接", result["message"])

    def test_trigger_blocked_while_measurement_running(self):
        manager = InstrumentManager()
        manager.microwave_resource = object()
        manager.microwave_state["connected"] = True
        manager.measurement_state["running"] = True
        result = manager.start_microwave_sweep_trigger()
        self.assertFalse(result["success"])
        self.assertIn("测量任务", result["message"])

    def test_stop_when_idle_is_ok(self):
        manager = InstrumentManager()
        result = manager.stop_microwave_sweep_trigger()
        self.assertTrue(result["success"])


if __name__ == "__main__":
    unittest.main()
