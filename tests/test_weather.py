import unittest
from unittest.mock import MagicMock, patch

from fishing.weather import open_meteo, open_meteo_multi


def _mock_client(hourly: dict) -> MagicMock:
    response = MagicMock()
    response.json.return_value = {"hourly": hourly}
    client = MagicMock()
    client.__enter__.return_value.get.return_value = response
    return client


class OpenMeteoParsingTests(unittest.TestCase):
    def test_single_model_tolerates_missing_and_short_hourly_fields(self) -> None:
        client = _mock_client({
            "time": ["2026-10-04T08:00", "2026-10-04T09:00"],
            "wind_speed_10m": [4.0],
        })

        with patch("fishing.weather._client", return_value=client):
            result = open_meteo(47.97, -122.65, hours=2)

        self.assertEqual(result["hours"][0]["wind_mph"], 4.0)
        self.assertIsNone(result["hours"][1]["wind_mph"])
        self.assertIsNone(result["hours"][0]["gust_mph"])
        self.assertIsNone(result["hours"][1]["wind_dir_deg"])

    def test_multi_model_tolerates_missing_and_short_wind_fields(self) -> None:
        client = _mock_client({
            "time": ["2026-10-04T08:00", "2026-10-04T09:00"],
            "temperature_2m": [54.0, 55.0],
            "precipitation": [0.0, 0.0],
            "wind_speed_10m_gfs_seamless": [4.0, 5.0],
            "wind_speed_10m_icon_seamless": [6.0, 7.0],
            "wind_gusts_10m_gfs_seamless": [8.0],
        })

        with patch("fishing.weather._client", return_value=client):
            result = open_meteo_multi(
                47.97,
                -122.65,
                hours=2,
                models=("gfs_seamless", "icon_seamless"),
            )

        self.assertEqual(len(result["hours"]), 2)
        self.assertEqual(result["hours"][0]["wind_mph"], 5.0)
        self.assertEqual(result["hours"][1]["wind_mph"], 6.0)
        self.assertEqual(result["hours"][0]["gust_mph"], 8.0)
        self.assertIsNone(result["hours"][1]["gust_mph"])
        self.assertIsNone(result["hours"][0]["wind_dir_deg"])


if __name__ == "__main__":
    unittest.main()
