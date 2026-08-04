import unittest

from fastapi.testclient import TestClient

from backend.app.main import app


class AccuracyApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def test_defaults(self) -> None:
        response = self.client.get("/api/accuracy/defaults")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("params", data)
        self.assertAlmostEqual(data["params"]["d_delta_f_dI_bus_khz_per_a"], 253.86666666666662)

    def test_map_theoretical(self) -> None:
        response = self.client.post(
            "/api/accuracy/map",
            json={
                "df_khz": 50,
                "quantity": "delta_f",
                "mode": "theoretical",
                "compare_standard": True,
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertAlmostEqual(data["result"]["delta_I_bus_a"], 50.0 / 253.86666666666662, places=8)
        self.assertTrue(any(item["within_limit"] for item in data["standard_comparison"]))

    def test_tables(self) -> None:
        response = self.client.post(
            "/api/accuracy/tables",
            json={"params": {"In_a": 3000}, "classes": ["0.2", "0.2S"]},
        )
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertGreaterEqual(len(data["abs_current_error"]), 8)
        self.assertGreaterEqual(len(data["freq_tolerance"]), 8)

    def test_export_csv(self) -> None:
        response = self.client.post(
            "/api/accuracy/export-csv/freq_tolerance",
            json={"params": {"In_a": 3000}, "classes": ["0.2S"]},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("text/csv", response.headers.get("content-type", ""))
        self.assertIn("delta_f_tol_khz", response.text)


if __name__ == "__main__":
    unittest.main()
