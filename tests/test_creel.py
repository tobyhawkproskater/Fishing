import unittest
from unittest.mock import patch

from fishing.creel import (
    HALIBUT_RULE_URL,
    _comparison_text,
    _fetch_html,
    _page_numbers,
    _render_halibut_section,
    aggregate,
    trend_summary,
)


class CreelPaginationTests(unittest.TestCase):
    def test_page_numbers_reads_pager_links(self) -> None:
        html = """
        <a href="?sample_date=3&amp;page=1">2</a>
        <a href="/fishing/reports/creel/puget?sample_date=3&amp;page=21">Last</a>
        """

        self.assertEqual(_page_numbers(html), {0, 1, 21})

    @patch("fishing.creel._fetch_page")
    def test_fetch_html_follows_every_page_through_last(self, fetch_page) -> None:
        fetch_page.side_effect = lambda page=0: (
            '<a href="?page=2">Last</a><table>page 0</table>'
            if page == 0
            else f"<table>page {page}</table>"
        )

        html = _fetch_html()

        self.assertEqual(fetch_page.call_args_list, [unittest.mock.call(), unittest.mock.call(1), unittest.mock.call(2)])
        self.assertIn("page 0", html)
        self.assertIn("page 1", html)
        self.assertIn("page 2", html)


class CreelSummaryTests(unittest.TestCase):
    def test_area_4_labels_are_aggregated_together(self) -> None:
        rows = [
            {
                "date": "2026-08-14",
                "catch_area": catch_area,
                "anglers": anglers,
                "interviews": 4,
                "coho": coho,
                "chinook": 0,
            }
            for catch_area, anglers, coho in (
                ("Area 4, Neah Bay", 20, 8),
                ("Area 4, Eastern portion", 10, 1),
            )
        ]

        points = aggregate(rows)

        self.assertEqual(len(points), 1)
        self.assertEqual(points[0]["area"], "MA4")
        self.assertEqual(points[0]["anglers"], 30)
        self.assertEqual(points[0]["coho_rate"], 0.3)

    def test_areas_8_1_and_8_2_are_aggregated_separately(self) -> None:
        rows = [
            {
                "date": "2026-08-14",
                "catch_area": catch_area,
                "anglers": 10,
                "interviews": 4,
                "coho": coho,
                "chinook": 0,
            }
            for catch_area, coho in (
                ("Area 8-1, Deception Pass, Hope Island, and Skagit Bay", 2),
                ("Area 8-2, Ports Susan and Gardner", 5),
            )
        ]

        points = aggregate(rows)

        self.assertEqual([point["area"] for point in points], ["MA8-1", "MA8-2"])
        self.assertEqual([point["coho_rate"] for point in points], [0.2, 0.5])

    def test_zero_baseline_catch_is_not_reported_as_missing_history(self) -> None:
        points = [
            {
                "date": f"2026-08-{day:02d}",
                "area": "MA9",
                "anglers": 10,
                "interviews": 5,
                "coho": 0 if day <= 7 else 5,
            }
            for day in range(1, 11)
        ]

        summary = trend_summary(points, "MA9")

        self.assertEqual(summary["baseline_days"], 7)
        self.assertEqual(summary["baseline_fish"], 0)
        self.assertEqual(
            _comparison_text(summary),
            "Prior 7 days: 0.00 (0 coho / 70 anglers)",
        )


class HalibutSectionTests(unittest.TestCase):
    def test_halibut_section_has_current_reopening_and_limits(self) -> None:
        html = _render_halibut_section()

        self.assertIn("Aug. 16-Sept. 30", html)
        self.assertIn("Marine Areas 5-10", html)
        self.assertIn("1 fish daily", html)
        self.assertIn("6 fish annually", html)
        self.assertIn("80,512 pounds", html)
        self.assertIn(HALIBUT_RULE_URL, html)


if __name__ == "__main__":
    unittest.main()