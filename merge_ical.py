"""
Merges Airbnb AND Vrbo iCal feeds for each house into one combined
calendar, plus one calendar per house.

Output:
  docs/cleaning.ics              -> ALL houses, ALL platforms combined
  docs/cleaning_<slug>.ics       -> one file PER house

For each house, two kinds of events are generated per reservation:
  1. A "stay" event spanning check-in to check-out (informational,
     matches what Airbnb/Vrbo show). Note: per the iCal spec, the
     checkout date itself is NOT rendered as part of a multi-day
     all-day event by most calendar apps (Apple Calendar included) --
     that's expected behavior for the underlying data.
  2. A dedicated single-day "Checkout / Cleaning" event placed
     EXACTLY on the checkout date, so it always shows up on that
     day. If the next reservation for the same house checks in on
     that same date, the event is flagged as a BACK-TO-BACK TURNOVER
     so the cleaning team knows they need to turn the house around
     same-day.

Each event is tagged with CATEGORIES = house name, so calendar apps
that support filtering/coloring by category (Outlook, Apple Calendar)
can sort by house automatically.
"""

import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import requests
from icalendar import Calendar, Event

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


def to_date(value) -> date:
    """Normalize a date/datetime value to a plain date."""
    if isinstance(value, datetime):
        return value.date()
    return value


def us_date(value: date) -> str:
    """Format a date as MM/DD/YYYY (US format)."""
    return value.strftime("%m/%d/%Y")


def collect_house_events(prop):
    """Fetch and combine reservations from all sources for one house,
    sorted by check-in date."""
    events = []
    for source in prop["sources"]:
        platform = source["platform"]
        url = source["ical_url"]
        try:
            cal = fetch_calendar(url)
        except Exception as e:
            print(f"[ERROR] {prop['name']} / {platform}: {e}", file=sys.stderr)
            continue

        for component in cal.walk():
            if component.name != "VEVENT":
                continue
            dtstart = component.get("dtstart")
            dtend = component.get("dtend")
            if dtstart is None or dtend is None:
                continue

            events.append(
                {
                    "platform": platform,
                    "summary": str(component.get("summary", "Reservation")),
                    "start": to_date(dtstart.dt),
                    "end": to_date(dtend.dt),  # exclusive checkout date
                }
            )

    events.sort(key=lambda e: e["start"])
    return events


def make_allday_event(uid: str, summary: str, start: date, end: date, categories: str) -> Event:
    """Create an all-day VEVENT spanning [start, end) (end exclusive,
    per iCal convention)."""
    ev = Event()
    ev.add("uid", uid)
    ev.add("summary", summary)
    ev.add("dtstart", start)
    ev.add("dtend", end)
    ev.add("categories", categories)
    return ev


def build_calendars(properties):
    global_cal = new_calendar("Cleaning schedule - all houses")
    per_house_cals = {}
    total_events = 0

    for prop in properties:
        name = prop["name"]
        slug = prop["slug"]
        house_cal = new_calendar(f"Cleaning schedule - {name}")

        reservations = collect_house_events(prop)

        for i, res in enumerate(reservations):
            platform = res["platform"]
            start = res["start"]
            checkout = res["end"]

            # 1) Informational "stay" event (check-in through the
            #    night before checkout, per iCal convention).
            stay_summary = (
                f"{name} ({platform}) - {res['summary']} "
                f"({us_date(start)} - {us_date(checkout)})"
            )
            stay_uid = f"stay-{slug}-{start.isoformat()}-{platform}@cleaning-sync"
            stay_event = make_allday_event(stay_uid, stay_summary, start, checkout, name)
            global_cal.add_component(stay_event)
            house_cal.add_component(stay_event)
            total_events += 1

            # 2) Dedicated checkout/cleaning marker, placed exactly on
            #    the checkout date so it's never hidden.
            is_back_to_back = (
                i + 1 < len(reservations) and reservations[i + 1]["start"] == checkout
            )
            checkout_summary = f"{name} - Checkout / Cleaning ({platform})"
            if is_back_to_back:
                checkout_summary += " -- BACK-TO-BACK TURNOVER, same-day check-in"

            checkout_uid = f"checkout-{slug}-{checkout.isoformat()}-{platform}@cleaning-sync"
            checkout_event = make_allday_event(
                checkout_uid,
                checkout_summary,
                checkout,
                checkout + timedelta(days=1),
                name,
            )
            global_cal.add_component(checkout_event)
            house_cal.add_component(checkout_event)
            total_events += 1

        per_house_cals[slug] = house_cal

    print(f"Total events created: {total_events}")
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
