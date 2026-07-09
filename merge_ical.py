#!/usr/bin/env python3
"""
Merges Airbnb AND Vrbo iCal feeds for each house into one combined
calendar, plus one calendar per house.

Output:
  docs/cleaning.ics              -> ALL houses, ALL platforms combined
  docs/cleaning_<slug>.ics       -> one file PER house (useful if the
                                     cleaning team wants to subscribe
                                     house by house)

Each event is labeled:
  "<House> (<Platform>) - <original title> (MM/DD/YYYY - MM/DD/YYYY)"
and tagged with CATEGORIES = house name, so calendar apps that support
filtering/coloring by category (Outlook, Apple Calendar) can sort by
house automatically.
"""

import json
import sys
from datetime import date, datetime
from pathlib import Path

import requests
from icalendar import Calendar

CONFIG_PATH = Path(__file__).parent / "config.json"
DOCS_DIR = Path(__file__).parent / "docs"


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["properties"]


def fetch_calendar(url: str) -> Calendar:
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return Calendar.from_ical(resp.content)


def new_calendar(name: str) -> Calendar:
    cal = Calendar()
    cal.add("prodid", "-//Multi-House Cleaning Sync//EN")
    cal.add("version", "2.0")
    cal.add("x-wr-calname", name)
    return cal


def us_date(value) -> str:
    """Format a date/datetime value as MM/DD/YYYY (US format)."""
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return value.strftime("%m/%d/%Y")
    return str(value)


def build_calendars(properties):
    global_cal = new_calendar("Cleaning schedule - all houses")
    per_house_cals = {}
    total_events = 0

    for prop in properties:
        name = prop["name"]
        slug = prop["slug"]
        house_cal = new_calendar(f"Cleaning schedule - {name}")

        for source in prop["sources"]:
            platform = source["platform"]
            url = source["ical_url"]
            try:
                cal = fetch_calendar(url)
            except Exception as e:
                print(f"[ERROR] {name} / {platform}: {e}", file=sys.stderr)
                continue

            for component in cal.walk():
                if component.name != "VEVENT":
                    continue

                original_summary = str(component.get("summary", "Reservation"))
                dtstart = component.get("dtstart")
                dtend = component.get("dtend")

                date_range = ""
                if dtstart is not None and dtend is not None:
                    start_str = us_date(dtstart.dt)
                    end_str = us_date(dtend.dt)
                    date_range = f" ({start_str} - {end_str})"

                component["summary"] = (
                    f"{name} ({platform}) - {original_summary}{date_range}"
                )
                component["categories"] = name  # enables filtering by house

                global_cal.add_component(component)
                house_cal.add_component(component)
                total_events += 1

        per_house_cals[slug] = house_cal

    print(f"Total events merged: {total_events}")
    return global_cal, per_house_cals


def write_calendar(cal: Calendar, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        f.write(cal.to_ical())
    print(f"Written: {path}")


def main():
    properties = load_config()
    global_cal, per_house_cals = build_calendars(properties)

    write_calendar(global_cal, DOCS_DIR / "cleaning.ics")
    for slug, cal in per_house_cals.items():
        write_calendar(cal, DOCS_DIR / f"cleaning_{slug}.ics")


if __name__ == "__main__":
    main()
