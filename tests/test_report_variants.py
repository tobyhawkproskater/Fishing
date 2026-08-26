import datetime as dt
import unittest

from fishing.html_loadout import render_nav
from fishing.html_report_ma9 import _render_daily_chart
from fishing.html_report_ma9_mobile import _render_daily_chart_mobile


class ReportVariantTests(unittest.TestCase):
    def test_big_jake_tab_follows_mobile(self) -> None:
        nav = render_nav("big-jake")

        self.assertLess(nav.index("Mobile"), nav.index("Big Jake"))
        self.assertLess(nav.index("Big Jake"), nav.index("Creel Trends"))
        self.assertIn("class='active' href='big-jake.html'", nav)

    def test_chart_supports_zero_tide_dock_reference(self) -> None:
        chart = _render_daily_chart_mobile(
            dt.date(2026, 8, 22), [], [], [], [],
            tide_reference_ft=0.0,
            tide_reference_label="0 ft dock elevator",
        )

        self.assertIn("0 ft dock elevator", chart)
        self.assertNotIn("+2 ft float", chart)

    def test_mobile_chart_labels_every_hour(self) -> None:
        chart = _render_daily_chart_mobile(dt.date(2026, 8, 22), [], [], [], [])

        self.assertEqual(chart.count("class='hour-tick-label'"), 25)
        self.assertEqual(chart.count(">12a</text>"), 2)
        self.assertIn(">12p</text>", chart)

    def test_wind_axis_tops_out_at_20_mph(self) -> None:
        renderers = (_render_daily_chart, _render_daily_chart_mobile)

        for render_chart in renderers:
            with self.subTest(renderer=render_chart.__name__):
                chart = render_chart(dt.date(2026, 8, 22), [], [], [], [])
                self.assertIn("fill='#D83B01'>20</text>", chart)
                self.assertNotIn("fill='#D83B01'>30</text>", chart)


if __name__ == "__main__":
    unittest.main()
