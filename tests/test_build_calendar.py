from datetime import date, datetime, timezone
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from build_calendar import CollectionEvent, parse_calendar_html, to_ical  # noqa: E402


class BuildCalendarTests(unittest.TestCase):
    def test_parses_collection_markers_across_months(self) -> None:
        html = """
        <article class="month-1">
          <article class="collecte-type-3"><span>2</span></article>
          <article class="collecte-type-1 collecte-type-2"><span>12</span></article>
        </article>
        <article class="month-2">
          <article class="collecte-type-2"><span>3</span></article>
        </article>
        """

        self.assertEqual(
            parse_calendar_html(html, 2026),
            [
                CollectionEvent(date(2026, 1, 2), "3"),
                CollectionEvent(date(2026, 1, 12), "1"),
                CollectionEvent(date(2026, 1, 12), "2"),
                CollectionEvent(date(2026, 2, 3), "2"),
            ],
        )

    def test_feed_omits_private_inputs(self) -> None:
        secret_address = "55 Example Street"
        secret_building_id = "999999"
        ical = to_ical(
            [CollectionEvent(date(2026, 1, 2), "3")],
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            "opaque-feed-token",
        )

        self.assertIn("SUMMARY:Compost collection\r\n", ical)
        self.assertNotIn(secret_address, ical)
        self.assertNotIn(secret_building_id, ical)
        self.assertNotIn("LOCATION:", ical)
        self.assertNotIn("URL:", ical)
        self.assertNotIn("METHOD:", ical)
        self.assertIn("@calendar-feed.invalid\r\n", ical)
        self.assertIn("BEGIN:VALARM\r\n", ical)
        self.assertIn("ACTION:DISPLAY\r\n", ical)
        self.assertIn("TRIGGER:-PT8H\r\n", ical)
        self.assertTrue(ical.startswith("BEGIN:VCALENDAR\r\n"))
        self.assertTrue(ical.endswith("END:VCALENDAR\r\n"))
        self.assertTrue(all(len(line.encode("utf-8")) <= 75 for line in ical.split("\r\n") if line))


if __name__ == "__main__":
    unittest.main()
