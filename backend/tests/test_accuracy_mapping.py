import math
import unittest

from backend.app.services.accuracy_mapping import (
    PlatformParams,
    abs_current_error_table,
    delta_I_a_to_delta_f_khz,
    delta_f_khz_to_delta_I_a,
    export_standard_csvs,
    freq_tolerance_table,
    max_pitch_angle_deg,
    ratio_error_table,
)


class AccuracyMappingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.params = PlatformParams()

    def test_zeeman_sensitivities(self) -> None:
        self.assertAlmostEqual(self.params.gamma_mhz_per_g(), 2.8, places=12)
        self.assertAlmostEqual(self.params.dB_dI_bus_gs_per_a(), 6.8 / 150.0, places=12)
        self.assertAlmostEqual(
            self.params.d_delta_f_dI_bus_khz_per_a(),
            253.86666666666662,
            places=8,
        )
        self.assertAlmostEqual(
            self.params.d_branch_f_dI_bus_khz_per_a(),
            126.93333333333331,
            places=8,
        )
        self.assertAlmostEqual(self.params.d_delta_f_dI_exc_mhz_per_a(), 38.08, places=8)
        self.assertAlmostEqual(self.params.max_bus_a(), 2250.0, places=8)
        self.assertAlmostEqual(self.params.max_bus_percent_In(), 75.0, places=8)

    def test_ratio_error_0_2s_points(self) -> None:
        rows = { (r.accuracy_class, r.I_percent_In): r for r in ratio_error_table(["0.2S"]) }
        self.assertEqual(rows[("0.2S", 1.0)].ratio_error_pm_percent, 0.75)
        self.assertEqual(rows[("0.2S", 5.0)].ratio_error_pm_percent, 0.35)
        self.assertEqual(rows[("0.2S", 20.0)].ratio_error_pm_percent, 0.2)
        self.assertEqual(rows[("0.2S", 100.0)].ratio_error_pm_percent, 0.2)

    def test_abs_error_in_3000(self) -> None:
        rows = {
            (r.accuracy_class, r.I_percent_In): r
            for r in abs_current_error_table(self.params, classes=["0.2S", "0.2"])
        }
        self.assertAlmostEqual(rows[("0.2S", 1.0)].abs_error_pm_a, 0.225, places=12)
        self.assertAlmostEqual(rows[("0.2S", 5.0)].abs_error_pm_a, 0.525, places=12)
        self.assertAlmostEqual(rows[("0.2S", 20.0)].abs_error_pm_a, 1.2, places=12)
        self.assertAlmostEqual(rows[("0.2S", 100.0)].abs_error_pm_a, 6.0, places=12)
        self.assertAlmostEqual(rows[("0.2", 5.0)].abs_error_pm_a, 1.125, places=12)
        self.assertFalse(rows[("0.2S", 100.0)].reachable_on_0_15A_platform)
        self.assertTrue(rows[("0.2S", 20.0)].reachable_on_0_15A_platform)

    def test_freq_tolerance_0_2s(self) -> None:
        rows = {
            r.I_percent_In: r
            for r in freq_tolerance_table(self.params, classes=["0.2S"])
        }
        self.assertAlmostEqual(rows[1.0].delta_f_tol_khz, 57.12, places=6)
        self.assertAlmostEqual(rows[1.0].branch_f_tol_khz, 28.56, places=6)
        self.assertAlmostEqual(rows[100.0].delta_f_tol_khz, 1523.2, places=4)

    def test_delta_f_to_current_theoretical(self) -> None:
        result = delta_f_khz_to_delta_I_a(50.0, quantity="delta_f", params=self.params)
        self.assertAlmostEqual(result.delta_I_bus_a, 50.0 / 253.86666666666662, places=10)
        inv = delta_I_a_to_delta_f_khz(result.delta_I_bus_a, quantity="delta_f")
        self.assertAlmostEqual(inv, 50.0, places=8)

        branch = delta_f_khz_to_delta_I_a(50.0, quantity="branch", params=self.params)
        self.assertAlmostEqual(branch.delta_I_bus_a, 50.0 / 126.93333333333331, places=10)

    def test_empirical_mode(self) -> None:
        # Lab calibration uses excitation amperes: 1 A_exc <-> 38.08 MHz splitting
        slope = 1.0 / 38.08e6
        result = delta_f_khz_to_delta_I_a(
            38.08,  # kHz -> 0.001 A_exc
            quantity="delta_f",
            mode="empirical",
            empirical_slope_a_per_hz=slope,
        )
        self.assertAlmostEqual(result.delta_I_exc_a, 0.001, places=12)
        self.assertAlmostEqual(result.delta_I_bus_a, 0.001 * 150.0, places=10)

        full = delta_f_khz_to_delta_I_a(
            38.08e3,  # 38.08 MHz in kHz
            quantity="delta_f",
            mode="empirical",
            empirical_slope_a_per_hz=slope,
        )
        self.assertAlmostEqual(full.delta_I_exc_a, 1.0, places=10)
        self.assertAlmostEqual(full.delta_I_bus_a, 150.0, places=8)

    def test_pitch_angle_0_2_percent(self) -> None:
        th = max_pitch_angle_deg(0.002)
        self.assertAlmostEqual(th, 3.62430749400795, places=6)

    def test_export_csvs(self) -> None:
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            paths = export_standard_csvs(tmp, self.params)
            for path in paths.values():
                self.assertTrue(Path(path).is_file())
                text = Path(path).read_text(encoding="utf-8-sig")
                self.assertGreater(len(text.splitlines()), 1)


if __name__ == "__main__":
    unittest.main()
