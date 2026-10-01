#!/usr/bin/env python3
"""Generate an iCalendar feed from a municipal collection schedule."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

CALENDAR_URL = "https://ville.saguenay.ca/collecte_calendrier"
TYPE_NAMES = {
    "1": "Garbage collection",
    "2": "Recycling collection",
    "3": "Compost collection",
}


@dataclass(frozen=True, order=True)
class CollectionEvent:
    collection_date: date
    collection_type: str


class CollectionCalendarParser(HTMLParser):
    """Extract dated collection-day markers from the municipality's calendar HTML."""

    def __init__(self, year: int) -> None:
        super().__init__(convert_charrefs=True)
        self.year = year
        self.month: int | None = None
        self.article_stack: list[tuple[str, ...] | None] = []
        self.events: list[CollectionEvent] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "article":
            return

        classes = dict(attrs).get("class") or ""
        month_match = re.search(r"\bmonth-(\d{1,2})\b", classes)
        if month_match:
            self.month = int(month_match.group(1))
            self.article_stack.append(None)
            return

        collection_types = tuple(re.findall(r"\bcollecte-type-(\d+)\b", classes))
        self.article_stack.append(collection_types or None)

    def handle_endtag(self, tag: str) -> None:
        if tag == "article" and self.article_stack:
            self.article_stack.pop()

    def handle_data(self, data: str) -> None:
        collection_types = next(
            (types for types in reversed(self.article_stack) if types), None
        )
        if collection_types is None:
            return

        day_text = data.strip()
        if not day_text.isdigit() or self.month is None:
            return

        collection_date = date(self.year, self.month, int(day_text))
        for collection_type in collection_types:
            if collection_type not in TYPE_NAMES:
                raise ValueError(f"Unknown collection type {collection_type!r}")
            self.events.append(CollectionEvent(collection_date, collection_type))


def required_environment(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ValueError(f"Missing required GitHub Actions secret: {name}")
    return value


def fetch_calendar_html(year: int, next_year: bool, building_id: str, address: str) -> str:
    params = urlencode(
        {
            "batiment": building_id,
            "annee_suivante": "1" if next_year else "0",
            "adresse": address,
        }
    )
    request = Request(
        f"{CALENDAR_URL}?{params}",
        headers={"User-Agent": "calendar-feed/1.0"},
    )
    with urlopen(request, timeout=30) as response:
        encoding = response.headers.get_content_charset() or "utf-8"
        html = response.read().decode(encoding)

    if not re.search(rf"Calendrier des matières résiduelles\s+{year}\b", html):
        raise ValueError(f"Municipal calendar did not return the expected {year} schedule")
    return html


def parse_calendar_html(html: str, year: int) -> list[CollectionEvent]:
    parser = CollectionCalendarParser(year)
    parser.feed(html)
    parser.close()
    return sorted(set(parser.events))


def fold_ical_line(line: str) -> str:
    """Fold an RFC 5545 content line at 75 UTF-8 octets."""
    chunks: list[str] = []
    chunk = ""
    for character in line:
        maximum_bytes = 75 if not chunks else 74
        if chunk and len((chunk + character).encode("utf-8")) > maximum_bytes:
            chunks.append(chunk)
            chunk = character
        else:
            chunk += character
    chunks.append(chunk)
    return "\r\n ".join(chunks)


def to_ical(events: list[CollectionEvent], generated_at: datetime, feed_token: str) -> str:
    stamp = generated_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    uid_namespace = hashlib.sha256(feed_token.encode("utf-8")).hexdigest()[:24]
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//calendar-feed//Household Collection Calendar//EN",
        "CALSCALE:GREGORIAN",
        "X-WR-CALNAME:Household collection",
    ]

    for event in events:
        collection_name = TYPE_NAMES[event.collection_type]
        next_day = event.collection_date + timedelta(days=1)
        uid = f"collection-{uid_namespace}-{event.collection_date:%Y%m%d}-{event.collection_type}@calendar-feed.invalid"
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{uid}",
                f"DTSTAMP:{stamp}",
                f"LAST-MODIFIED:{stamp}",
                f"DTSTART;VALUE=DATE:{event.collection_date:%Y%m%d}",
                f"DTEND;VALUE=DATE:{next_day:%Y%m%d}",
                f"SUMMARY:{collection_name}",
                "BEGIN:VALARM",
                "ACTION:DISPLAY",
                f"DESCRIPTION:{collection_name} tomorrow",
                "TRIGGER:-PT8H",
                "END:VALARM",
                "END:VEVENT",
            ]
        )

    lines.append("END:VCALENDAR")
    return "\r\n".join(fold_ical_line(line) for line in lines) + "\r\n"


def build_calendar(year: int, building_id: str, address: str) -> list[CollectionEvent]:
    events: list[CollectionEvent] = []
    for next_year in (False, True):
        calendar_year = year + int(next_year)
        html = fetch_calendar_html(calendar_year, next_year, building_id, address)
        events.extend(parse_calendar_html(html, calendar_year))

    unique_events = sorted(set(events))
    if not unique_events:
        raise ValueError("No collection dates were found in either municipal calendar")
    return unique_events


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=date.today().year)
    args = parser.parse_args()

    try:
        building_id = required_environment("SAGUENAY_BUILDING_ID")
        address = required_environment("SAGUENAY_ADDRESS")
        feed_token = required_environment("CALENDAR_FEED_TOKEN")
        events = build_calendar(args.year, building_id, address)
    except Exception as error:
        print(f"Calendar generation failed: {error}", file=sys.stderr)
        return 1

    output = Path("site") / f"{feed_token}.ics"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(to_ical(events, datetime.now(timezone.utc), feed_token), encoding="utf-8")
    print(f"Wrote {len(events)} collection events")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
