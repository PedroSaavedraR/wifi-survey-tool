import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from validation.practica2_analysis import (
    build_observations,
    load_captures,
    observations_with_distances,
    select_signal_metric,
    summarize_access_points,
    summarize_signal_methods,
)
from validation.map_measurements import (
    build_router_coverage_models,
    load_access_point_inventory,
    load_map_measurements,
    summarize_router_eduroam_signal,
)
from wifi_scanner import (
    get_active_connection,
    get_visible_networks,
    measurement_position,
    output_path_for_mode,
)


class PracticeTwoAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.records = [
            {
                "metadata": {
                    "timestamp_utc": "2026-10-01T10:00:00+00:00",
                    "session_id": "session-1",
                    "sample_index": 1,
                    "room": "P1",
                    "position": {
                        "point_id": "P1",
                        "plan_id": "floor-1",
                        "units": "px",
                        "x": 3,
                        "y": 4,
                    },
                },
                "active_interface": {
                    "status": "connected",
                    "bssid_hash": "ap-hash",
                    "rssi_dbm": -60,
                },
                "visible_networks": [{
                    "ssid": "test-network",
                    "bssids": [{
                        "bssid_hash": "ap-hash",
                        "signal_percent": 70,
                    }],
                }],
            },
            {
                "metadata": {"room": "P1"},
                "active_interface": {},
                "visible_networks": [{
                    "ssid": "test-network",
                    "bssids": [{
                        "bssid_hash": "ap-hash",
                        "signal_percent": 0,
                    }],
                }],
            },
        ]
        self.observations = build_observations(self.records)

    def test_build_observations_preserves_units_and_legacy_positions(self):
        first, second = self.observations
        self.assertEqual(first["point_id"], "P1")
        self.assertEqual(first["rssi_dbm"], -60)
        self.assertEqual(first["signal_percent"], 70)
        self.assertIsNone(second["x"])
        self.assertEqual(second["signal_percent"], 0)
        self.assertEqual(first["bssid"], "ap-hash")

    def test_summary_counts_connections_and_does_not_drop_zero(self):
        summary = summarize_access_points(self.observations, "P1")
        self.assertEqual(summary[0]["detections"], 2)
        self.assertEqual(summary[0]["connected_captures"], 1)
        self.assertEqual(summary[0]["median_signal_percent"], 35)
        self.assertEqual(select_signal_metric(self.observations, "ap-hash"), ("rssi_dbm", "dBm"))

    def test_distance_requires_matching_plan_and_ap_position(self):
        ap_positions = [{
            "bssid_hash": "ap-hash",
            "plan_id": "floor-1",
            "x": 0,
            "y": 0,
            "units": "px",
        }]
        distances = observations_with_distances(
            self.observations,
            ap_positions,
            "ap-hash",
        )
        self.assertEqual(len(distances), 1)
        self.assertEqual(distances[0]["distance"], 5)
        self.assertEqual(distances[0]["distance_units"], "px")
        self.assertEqual(
            observations_with_distances(
                self.observations,
                [{**ap_positions[0], "plan_id": "another-floor"}],
                "ap-hash",
            ),
            [],
        )

    def test_distance_can_be_calibrated_to_meters(self):
        ap_positions = [{
            "bssid_hash": "ap-hash",
            "plan_id": "floor-1",
            "x": 0,
            "y": 0,
            "units": "px",
            "meters_per_unit": 0.1,
        }]
        distances = observations_with_distances(
            self.observations,
            ap_positions,
            "ap-hash",
            default_meters_per_unit=0.1,
        )
        self.assertEqual(distances[0]["distance"], 0.5)
        self.assertEqual(distances[0]["distance_units"], "m")

    def test_raw_bssid_matches_configured_access_point_position(self):
        bssid = "AA:BB:CC:DD:EE:FF"
        observations = build_observations([{
            "metadata": {
                "position": {
                    "point_id": "P1",
                    "plan_id": "floor-1",
                    "units": "px",
                    "x": 3,
                    "y": 4,
                },
            },
            "active_interface": {
                "status": "connected",
                "bssid": bssid,
                "rssi_dbm": -60,
            },
            "visible_networks": [{
                "ssid": "test-network",
                "bssids": [{"bssid": bssid, "signal_percent": 70}],
            }],
        }])

        self.assertEqual(observations[0]["bssid"], bssid)
        distances = observations_with_distances(
            observations,
            [{
                "bssid": bssid,
                "plan_id": "floor-1",
                "x": 0,
                "y": 0,
                "units": "px",
            }],
            bssid,
        )
        self.assertEqual(distances[0]["distance"], 5)

    def test_scanner_stores_unhashed_bssid_mac_addresses(self):
        with patch(
            "wifi_scanner.run_cmd",
            return_value="State : connected\nSSID : test-network\nBSSID : AA:BB:CC:DD:EE:FF\n",
        ):
            active = get_active_connection()
        self.assertEqual(active["bssid"], "AA:BB:CC:DD:EE:FF")
        self.assertNotIn("bssid_hash", active)

        with patch(
            "wifi_scanner.run_cmd",
            return_value=(
                "SSID 1 : test-network\n"
                "    BSSID 1 : AA:BB:CC:DD:EE:FF\n"
                "    Signal : 70%\n"
            ),
        ):
            networks = get_visible_networks()
        self.assertEqual(networks[0]["bssids"][0]["bssid"], "AA:BB:CC:DD:EE:FF")
        self.assertNotIn("bssid_hash", networks[0]["bssids"][0])

    def test_signal_summary_compares_dbm_and_linear_power_methods(self):
        summary = summarize_signal_methods(self.observations, "P1", "ap-hash")
        self.assertEqual(summary["valid_rssi_observations"], 1)
        self.assertEqual(summary["mean_rssi_dbm"], -60)
        self.assertEqual(summary["median_rssi_dbm"], -60)
        self.assertAlmostEqual(summary["median_power_mw"], 0.000001)
        self.assertAlmostEqual(summary["median_power_converted_dbm"], -60)

    def test_loader_reports_malformed_json_with_line_number(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            capture = Path(temporary_directory) / "screenshots.jsonl"
            capture.write_text("{invalid json}\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, r"screenshots\.jsonl, line 1"):
                load_captures(temporary_directory)

    def test_measurement_position_requires_complete_reference_and_coordinates(self):
        args = SimpleNamespace(x=3, y=4, point_id="P1", room="Room 1")
        with self.assertRaisesRegex(ValueError, "coordinate_reference.units"):
            measurement_position(args, {"coordinate_reference": {"plan_id": "floor-1"}})

        gui_args = SimpleNamespace(
            x=3,
            y=4,
            point_id="P1",
            room="P1",
            plan_id="FIC-P2",
            map_file="C:\\plans\\FIC - P2.png",
            building="FIC",
            floor="P2",
            coordinate_system="image_pixels_top_left",
            units="px",
            origin="top_left",
            x_axis="right",
            y_axis="down",
        )
        position = measurement_position(gui_args, {})
        self.assertEqual(position["plan_id"], "FIC-P2")
        self.assertEqual(position["map_file"], "C:\\plans\\FIC - P2.png")
        self.assertEqual(position["floor"], "P2")
        self.assertEqual(position["units"], "px")
        self.assertEqual(position["coordinate_system"], "image_pixels_top_left")

        reference = {
            "plan_id": "floor-1",
            "coordinate_system": "image_pixels_top_left",
            "units": "px",
            "origin": "top_left",
            "x_axis": "right",
            "y_axis": "down",
        }
        position = measurement_position(args, {"coordinate_reference": reference})
        self.assertEqual((position["x"], position["y"]), (3, 4))
        self.assertEqual(position["plan_id"], "floor-1")

    def test_practice_two_dataset_does_not_change_practice_one_paths(self):
        self.assertEqual(output_path_for_mode(False), os.path.join("data", "screenshots.jsonl"))
        self.assertEqual(output_path_for_mode(True), os.path.join("data", "screenshots_all.jsonl"))
        self.assertEqual(
            output_path_for_mode(False, "practica2"),
            os.path.join("data", "practica2", "screenshots.jsonl"),
        )
        self.assertEqual(
            output_path_for_mode(True, "practica2"),
            os.path.join("data", "practica2", "screenshots_all.jsonl"),
        )

    def test_map_measurements_summarize_signal_and_connected_link_rates(self):
        records = [
            {
                "metadata": {
                    "position": {"plan_id": "FIC-P3", "point_id": "P3-A", "x": 100, "y": 200},
                    "session_id": "session-1",
                },
                "active_interface": {
                    "status": "connected",
                    "bssid": "AA:BB:CC:DD:EE:FF",
                    "ssid": "connected-network",
                    "signal_percent": 80,
                    "rssi_dbm": -60,
                    "rx_rate_mbps": 300,
                    "tx_rate_mbps": 144,
                    "band": "5 GHz",
                    "channel": 36,
                },
                "visible_networks": [
                    {"ssid": "connected-network", "bssids": [
                        {"bssid": "AA:BB:CC:DD:EE:FF", "signal_percent": 80, "channel": 36},
                        {"bssid": "AA:BB:CC:DD:EE:FF", "signal_percent": 80, "channel": 36},
                    ]},
                    {"ssid": "neighbor-network", "bssids": [
                        {"bssid": "11:22:33:44:55:66", "signal_percent": 40, "channel": 1},
                    ]},
                ],
            },
            {
                "metadata": {
                    "position": {"plan_id": "FIC-P3", "point_id": "P3-A", "x": 100, "y": 200},
                    "session_id": "session-1",
                },
                "active_interface": {
                    "status": "connected",
                    "bssid": "AA:BB:CC:DD:EE:FF",
                    "ssid": "connected-network",
                    "signal_percent": 70,
                    "rssi_dbm": -66,
                    "rx_rate_mbps": 200,
                    "tx_rate_mbps": 100,
                },
                "visible_networks": [
                    {"ssid": "connected-network", "bssids": [
                        {"bssid": "AA:BB:CC:DD:EE:FF", "signal_percent": 70},
                    ]},
                ],
            },
        ]
        with tempfile.TemporaryDirectory() as temporary_directory:
            capture_file = Path(temporary_directory) / "screenshots_all.jsonl"
            capture_file.write_text(
                "".join(json.dumps(record) + "\n" for record in records),
                encoding="utf-8",
            )
            points = load_map_measurements(temporary_directory, "FIC-P3")

        point = points[(100, 200)]
        self.assertEqual(point["capture_count"], 2)
        self.assertEqual(point["sessions"], 1)
        self.assertEqual(point["point_ids"], ["P3-A"])
        connected, neighbor = point["networks"]
        self.assertEqual(connected["bssid"], "AA:BB:CC:DD:EE:FF")
        self.assertEqual(connected["detections"], 2)
        self.assertEqual(connected["connected_captures"], 2)
        self.assertEqual(connected["mean_signal_percent"], 75)
        self.assertEqual(connected["mean_rssi_dbm"], -63)
        self.assertEqual(connected["mean_rx_rate_mbps"], 250)
        self.assertEqual(connected["mean_tx_rate_mbps"], 122)
        self.assertEqual(neighbor["bssid"], "11:22:33:44:55:66")
        self.assertEqual(neighbor["mean_signal_percent"], 40)
        self.assertIsNone(neighbor["mean_rx_rate_mbps"])
        self.assertEqual(load_map_measurements(temporary_directory, "FIC-P2"), {})

    def test_map_measurements_still_reads_historical_hashed_bssid_fields(self):
        record = {
            "metadata": {
                "position": {"plan_id": "FIC-P3", "x": 10, "y": 20},
            },
            "active_interface": {
                "status": "connected",
                "bssid_hash": "legacy-ap-hash",
            },
            "visible_networks": [{
                "ssid": "legacy-network",
                "bssids": [{"bssid_hash": "legacy-ap-hash", "signal_percent": 60}],
            }],
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            capture_file = Path(temporary_directory) / "screenshots.jsonl"
            capture_file.write_text(json.dumps(record) + "\n", encoding="utf-8")
            points = load_map_measurements(temporary_directory, "FIC-P3")

        self.assertEqual(points[(10, 20)]["networks"][0]["bssid"], "legacy-ap-hash")

    def test_router_signal_uses_best_direct_eduroam_bssid_from_mac_family(self):
        point = {"networks": [
            {
                "bssid": "AA:BB:CC:DD:EE:60",
                "ssid": "eduroam",
                "mean_signal_percent": 40,
                "signal_observation_count": 2,
            },
            {
                "bssid": "aa:bb:cc:dd:ee:70",
                "ssid": "eduroam",
                "mean_signal_percent": 65,
                "signal_observation_count": 3,
            },
            {
                "bssid": "AA:BB:CC:DD:EE:71",
                "ssid": "other-network",
                "mean_signal_percent": 100,
                "signal_observation_count": 4,
            },
            {
                "bssid": "FF:BB:CC:DD:EE:70",
                "ssid": "eduroam",
                "mean_signal_percent": 95,
                "signal_observation_count": 1,
            },
            {
                "bssid": "11:22:33:44:55:60",
                "ssid": "eduroam",
                "mean_signal_percent": None,
                "signal_observation_count": 0,
            },
        ]}
        access_points = [
            {
                "name": "router-2.0",
                "radio_mac": "AA:BB:CC:DD:EE:70",
                "bssid_prefix": "AA:BB:CC:DD:EE",
                "x": 10,
                "y": 20,
            },
            {
                "name": "router-heard-without-level",
                "radio_mac": "11:22:33:44:55:60",
                "bssid_prefix": "11:22:33:44:55",
                "x": 25,
                "y": 35,
            },
            {
                "name": "router-not-heard",
                "radio_mac": "22:33:44:55:66:60",
                "bssid_prefix": "22:33:44:55:66",
                "x": 30,
                "y": 40,
            },
        ]

        summaries = summarize_router_eduroam_signal(point, access_points)

        self.assertEqual(summaries[0]["mean_signal_percent"], 65)
        self.assertEqual(summaries[0]["bssid"], "aa:bb:cc:dd:ee:70")
        self.assertEqual(summaries[0]["signal_observation_count"], 3)
        self.assertTrue(summaries[0]["detected"])
        self.assertTrue(summaries[1]["detected"])
        self.assertIsNone(summaries[1]["mean_signal_percent"])
        self.assertEqual(summaries[1]["signal_observation_count"], 0)
        self.assertFalse(summaries[2]["detected"])

    def test_ap_inventory_matches_radio_macs_and_p2_plan_positions(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            inventory_file = Path(temporary_directory) / "ap_list.csv"
            inventory_file.write_text(
                "Dispositivo,Dirección MAC de radio,Dirección MAC LAN,Tipo\n"
                "INFOR-A04-2-06-2116,98:8F:00:39:B4:20,,Aruba AP 655\n"
                "INFOR-A04-3-05-2117,98:8F:00:39:AB:B0,,Aruba AP 655\n",
                encoding="utf-8",
            )

            access_points = load_access_point_inventory(
                inventory_file,
                "FIC-P2",
            )

        self.assertEqual(len(access_points), 1)
        self.assertEqual(access_points[0]["name"], "INFOR-A04-2-06-2116")
        self.assertEqual(access_points[0]["bssid_prefix"], "98:8F:00:39:B4")
        self.assertEqual((access_points[0]["x"], access_points[0]["y"]), (803, 273))

    def test_router_coverage_estimates_concentric_radii_from_signal_by_distance(self):
        access_point = {
            "name": "router",
            "radio_mac": "AA:BB:CC:DD:EE:10",
            "bssid_prefix": "AA:BB:CC:DD:EE",
            "x": 0,
            "y": 0,
        }
        values = {
            (10, 0): 90,
            (110, 0): 10,
        }
        points = {
            position: {"networks": [{
                "bssid": f"AA:BB:CC:DD:EE:{index:02X}",
                "ssid": "eduroam",
                "mean_signal_percent": signal,
                "signal_observation_count": 10,
            }]}
            for index, (position, signal) in enumerate(values.items(), 16)
        }

        model = build_router_coverage_models(points, [access_point])[0]

        self.assertTrue(model["supported"])
        self.assertAlmostEqual(model["slope"], -0.8)
        self.assertAlmostEqual(model["intercept"], 98)
        self.assertAlmostEqual(model["radius_70"], 35)
        self.assertAlmostEqual(model["radius_40"], 72.5)
        self.assertEqual(model["max_radius"], 110)

    def test_router_coverage_requires_two_distinct_measured_distances(self):
        access_point = {
            "name": "router",
            "radio_mac": "AA:BB:CC:DD:EE:10",
            "bssid_prefix": "AA:BB:CC:DD:EE",
            "x": 0,
            "y": 0,
        }
        points = {
            (100, 0): {"networks": [{
                "bssid": "AA:BB:CC:DD:EE:10",
                "ssid": "eduroam",
                "mean_signal_percent": 80,
                "signal_observation_count": 1,
            }]},
            (0, 100): {"networks": [{
                "bssid": "AA:BB:CC:DD:EE:10",
                "ssid": "eduroam",
                "mean_signal_percent": 60,
                "signal_observation_count": 1,
            }]},
        }

        model = build_router_coverage_models(points, [access_point])[0]

        self.assertFalse(model["supported"])
        self.assertIsNone(model["radius_70"])
        self.assertIsNone(model["radius_40"])


if __name__ == "__main__":
    unittest.main()
