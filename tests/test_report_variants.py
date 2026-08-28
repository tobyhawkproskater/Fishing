import datetime as dt
import unittest

from fishing.html_loadout import render_nav
from fishing.html_report_ma9 import (
    _fmt_hour_float_clock, _render_daily_chart, _tide_ref_crossings,
)
from fishing.html_report_ma9_mobile import _render_daily_chart_mobile


def _sample_tide_day() -> tuple[
    list[tuple[dt.datetime, float, str]], list[dict],
]:
    """L (-0.5ft) -> H (4.5ft) -> L (-0.5ft) straddling both the 2.0ft and
    0.0ft references, giving one rising (IN) and one falling (OUT) crossing
    for either reference line."""
    day = dt.date(2026, 8, 22)
    raw = [
        {"t": "2026-08-22 03:00", "v": -0.5, "type": "L"},
        {"t": "2026-08-22 09:00", "v": 4.5, "type": "H"},
        {"t": "2026-08-22 15:00", "v": -0.5, "type": "L"},
    ]
    events_dt = [
        (dt.datetime.strptime(ev["t"], "%Y-%m-%d %H:%M"), float(ev["v"]), ev["type"])
        for ev in raw
    ]
    return events_dt, raw


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

    def test_tide_ref_crossings_detects_rising_and_falling(self) -> None:
        tide_pts = [(3.0, 0.5), (9.0, 4.5), (15.0, 0.5)]

        crossings = _tide_ref_crossings(tide_pts, 2.0)

        self.assertEqual([rising for _, rising in crossings], [True, False])
        hours = [hr for hr, _ in crossings]
        self.assertTrue(3.0 < hours[0] < 9.0)
        self.assertTrue(9.0 < hours[1] < 15.0)

    def test_fmt_hour_float_clock(self) -> None:
        self.assertEqual(_fmt_hour_float_clock(5.7), "5:42a")
        self.assertEqual(_fmt_hour_float_clock(0.0), "12:00a")
        self.assertEqual(_fmt_hour_float_clock(13.5), "1:30p")

    def test_charts_label_reference_line_in_and_out_times(self) -> None:
        events_dt, raw_tides = _sample_tide_day()
        day = dt.date(2026, 8, 22)

        desktop = _render_daily_chart(day, [], [], events_dt, raw_tides)
        self.assertEqual(desktop.count(">IN "), 1)
        self.assertEqual(desktop.count(">OUT "), 1)

        mobile = _render_daily_chart_mobile(day, [], [], events_dt, raw_tides)
        self.assertEqual(mobile.count(">IN "), 1)
        self.assertEqual(mobile.count(">OUT "), 1)

    def test_chart_without_tide_data_has_no_in_out_labels(self) -> None:
        chart = _render_daily_chart(dt.date(2026, 8, 22), [], [], [], [])

        self.assertNotIn(">IN ", chart)
        self.assertNotIn(">OUT ", chart)

    def test_big_jake_zero_reference_gets_its_own_crossings(self) -> None:
        """Big Jake's 0ft reference should cross where the +2ft one wouldn't."""
        events_dt, raw_tides = _sample_tide_day()
        day = dt.date(2026, 8, 22)

        chart = _render_daily_chart_mobile(
            day, [], [], events_dt, raw_tides,
            tide_reference_ft=0.0, tide_reference_label="0 ft dock elevator",
        )

        self.assertEqual(chart.count(">IN "), 1)
        self.assertEqual(chart.count(">OUT "), 1)


if __name__ == "__main__":
    unittest.main()
