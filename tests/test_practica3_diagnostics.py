import unittest

from validation.practica3_diagnostics import (
    band_for_channel,
    collect_ssid_observations,
    summarize_bssids,
)


class PracticeThreeDiagnosticsTests(unittest.TestCase):
    def test_channel_is_classified_into_wifi_band(self):
        self.assertEqual(band_for_channel(9), "2.4 GHz")
        self.assertEqual(band_for_channel("48"), "5 GHz")
        self.assertEqual(band_for_channel(None), "unknown")

    def test_signal_summaries_keep_distinct_bssids_separate(self):
        records = [{
            "metadata": {"position": {"point_id": "P1"}},
            "visible_networks": [{
                "ssid": "eduroam",
                "bssids": [
                    {"bssid": "AA:00:00:00:00:01", "channel": 1, "signal_percent": 30},
                    {"bssid": "AA:00:00:00:00:02", "channel": 36, "signal_percent": 80},
                ],
            }],
        }]
        observations = collect_ssid_observations(records, "eduroam")
        summaries = summarize_bssids(observations)
        self.assertEqual(len(summaries), 2)
        self.assertEqual(
            {(row["bssid"], row["band"], row["mean_signal_percent"]) for row in summaries},
            {
                ("AA:00:00:00:00:01", "2.4 GHz", 30.0),
                ("AA:00:00:00:00:02", "5 GHz", 80.0),
            },
        )

    def test_missing_signal_is_not_replaced_with_zero(self):
        observations = collect_ssid_observations([{
            "visible_networks": [{
                "ssid": "eduroam",
                "bssids": [{
                    "bssid": "AA:00:00:00:00:01",
                    "channel": 1,
                }],
            }],
        }], "eduroam")
        self.assertEqual(len(observations), 1)
        self.assertIsNone(observations[0]["signal_percent"])
        self.assertEqual(summarize_bssids(observations), [])


if __name__ == "__main__":
    unittest.main()
