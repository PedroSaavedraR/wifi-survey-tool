import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from validation.practica3_analysis import (
    _filter_model_rows,
    analyze_propagation_dataset,
    compare_propagation_models,
    fit_log_distance_exponent,
    measure_reference_level,
    write_model_metrics_csv,
)


class PracticeThreeAnalysisTests(unittest.TestCase):
    def test_fit_log_distance_exponent_recovers_path_loss_exponent(self):
        rows = [
            {"distance_m": 1.0, "rssi_dbm": -50.0},
            {"distance_m": 2.0, "rssi_dbm": -56.02059991327962},
            {"distance_m": 4.0, "rssi_dbm": -62.04119982655924},
            {"distance_m": 8.0, "rssi_dbm": -68.06179973983885},
            {"distance_m": 16.0, "rssi_dbm": -74.08239965311848},
        ]
        fit = fit_log_distance_exponent(rows, 1.0)
        self.assertAlmostEqual(fit["n"], 2.0, places=6)
        self.assertAlmostEqual(fit["A"], -50.0, places=6)
        self.assertAlmostEqual(fit["sigma"], 0.0, places=9)

    def test_fit_uses_free_reference_level_and_requires_multiple_distances(self):
        rows = [
            {"distance_m": 2.0, "rssi_dbm": -60.0},
            {"distance_m": 4.0, "rssi_dbm": -66.02059991327962},
            {"distance_m": 8.0, "rssi_dbm": -72.04119982655924},
        ]
        fit = fit_log_distance_exponent(rows, 1.0)
        self.assertAlmostEqual(fit["n"], 2.0, places=6)
        self.assertAlmostEqual(fit["A"], -53.97940008672037, places=6)

        one_distance = [
            {"distance_m": 8.0, "rssi_dbm": -60.0},
            {"distance_m": 8.0, "rssi_dbm": -62.0},
        ]
        with self.assertRaisesRegex(ValueError, "signal_percent"):
            fit_log_distance_exponent(one_distance, 1.0)

    def test_fit_can_hold_a_measured_reference_level_fixed(self):
        rows = [
            {"distance_m": 3.0, "rssi_dbm": -50.0, "point_id": "reference"},
            {"distance_m": 3.0, "rssi_dbm": -52.0, "point_id": "reference"},
            {"distance_m": 9.0, "rssi_dbm": -60.54242509439325, "point_id": "far"},
            {"distance_m": 9.0, "rssi_dbm": -60.54242509439325, "point_id": "far"},
        ]
        reference = measure_reference_level(rows, "reference")
        fit = fit_log_distance_exponent(rows, reference["d0"], reference_A=reference["A"])
        summary = compare_propagation_models(
            rows,
            reference["d0"],
            reference_A=reference["A"],
        )
        self.assertAlmostEqual(reference["A"], -51.0)
        self.assertAlmostEqual(reference["sigma"], 1.0)
        self.assertEqual(reference["measurements"], 2)
        self.assertAlmostEqual(fit["n"], 2.0, places=9)
        self.assertAlmostEqual(summary["model_1"]["A"], -51.0)
        self.assertAlmostEqual(summary["model_2"]["A"], -51.0)

    def test_vertical_separation_produces_a_valid_distance_at_same_plan_coordinate(self):
        rows = _filter_model_rows(
            [{
                "bssid": "00:11:22:33:44:55",
                "x": 100,
                "y": 100,
                "rssi_dbm": -50.0,
                "point_id": "under-ap",
            }],
            "00:11:22:33:44:55",
            access_points=[{
                "bssid": "00:11:22:33:44:55",
                "x": 100,
                "y": 100,
            }],
            default_meters_per_unit=0.1,
            delta_h_m=3.0,
        )
        self.assertAlmostEqual(rows[0]["distance_m"], 3.0)

    def test_compare_models_reports_mae_and_rmse_for_fixed_and_fitted_models(self):
        rows = [
            {"distance_m": 1.0, "rssi_dbm": -50.0},
            {"distance_m": 2.0, "rssi_dbm": -56.02059991327962},
            {"distance_m": 4.0, "rssi_dbm": -62.04119982655924},
            {"distance_m": 8.0, "rssi_dbm": -68.06179973983885},
        ]
        summary = compare_propagation_models(rows, 1.0, fixed_n=2.0)
        self.assertIn("model_1", summary)
        self.assertIn("model_2", summary)
        self.assertGreater(summary["model_2"]["MAE"], 0.0)
        self.assertGreater(summary["model_2"]["RMSE"], 0.0)
        self.assertAlmostEqual(summary["A"], -50.0, places=9)
        self.assertAlmostEqual(summary["d0"], 1.0, places=9)

    def test_metrics_csv_exports_both_models_and_reference_metadata(self):
        summary = {
            "d0": 3.0,
            "total_measurements": 4,
            "model_1": {
                "n": 2.0,
                "A": -50.0,
                "MAE": 2.0,
                "RMSE": 2.5,
                "sigma": None,
            },
            "model_2": {
                "n": 1.75,
                "A": -50.0,
                "MAE": 1.5,
                "RMSE": 2.0,
                "sigma": 2.0,
            },
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "nested" / "metrics.csv"
            write_model_metrics_csv(summary, output_path)
            lines = output_path.read_text(encoding="utf-8").splitlines()

        self.assertEqual(lines[0], "model,n,A_dBm,d0_m,MAE_dB,RMSE_dB,sigma_dB,measurements")
        self.assertIn("fixed_n_2,2.0,-50.0,3.0,2.0,2.5,,4", lines[1])
        self.assertIn("fitted_n,1.75,-50.0,3.0,1.5,2.0,2.0,4", lines[2])

    def test_explicit_inventory_errors_are_not_silently_ignored(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            (data_dir / "screenshots_all.jsonl").write_text("", encoding="utf-8")
            with patch("validation.practica3_analysis.build_observations", return_value=[]):
                with patch(
                    "validation.map_measurements.load_access_point_inventory",
                    side_effect=FileNotFoundError("inventory not found"),
                ):
                    with self.assertRaisesRegex(FileNotFoundError, "inventory not found"):
                        analyze_propagation_dataset(
                            data_dir,
                            "00:11:22:33:44:55",
                            1.0,
                            inventory_path="missing.csv",
                            plan_id="FIC-P2",
                        )


if __name__ == "__main__":
    unittest.main()
