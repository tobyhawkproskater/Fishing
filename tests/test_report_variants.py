import datetime as dt
import unittest

from fishing.html_loadout import render_nav
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


if __name__ == "__main__":
    unittest.main()
