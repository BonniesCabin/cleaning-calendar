"""
Merges Airbnb AND Vrbo iCal feeds for each house into one combined
calendar, plus one calendar per house.

Output:
  docs/cleaning.ics              -> ALL houses, ALL platforms combined
  docs/cleaning_<slug>.ics       -> one file PER house

For each real reservation, three events are generated:
  1. A "stay" event spanning check-in to check-out (all-day).
  2. A timed CHECK-IN event at 3:00 PM on the check-in date.
  3. A timed CHECKOUT / CLEANING event at 11:00 AM on the checkout
     date, flagged BACK-TO-BACK if the next reservation starts that
     same day.

"Not available" / blocked entries (manual blocks or cross-sync echoes
from the other platform) are skipped -- they are not real bookings.

Times: CHECKIN_HOUR / CHECKOUT_HOUR. Timezone via config.json
"timezone" key (defaults to America/Los_Angeles).
"""

import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from icalendar import Calendar, Event

CONFIG_PATH = Path(__file__).parent / "config.json"
DOCS_DIR = Path(__file__).parent / "docs"

CHECKIN_HOUR = 15   # 3:00 PM
CHECKOUT_HOUR = 11  # 11:00 AM
DEFAULT_TIMEZONE = "America/Los_Angeles"
EVENT_DURATION_HOURS = 1


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    tz_name = data.get("timezone", DEFAULT_TIMEZONE)
    return data["properties"], ZoneInfo(tz_name)


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
    if isinstance(value, datetime):
        return value.date()
    return value


def us_date(value: date) -> str:
    return value.strftime("%m/%d/%Y")


def collect_house_events(prop):
    """Fetch and combine reservations from all sources for one house,
    sorted by check-in date. Blocked / not-available entries are skipped."""
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

            summary = str(component.get("summary", "Reservation"))

            # Skip "blocked / not available" entries. These are NOT real
            # guest reservations -- they're manual blocks or cross-sync
            # echoes (e.g. an Airbnb feed re-exporting a Vrbo booking as
            # "Not available"). Real reservations use titles like
            # "Reserved". We drop anything that looks like a block.
            lowered = summary.lower()
            block_markers = (
                "not available",
                "unavailable",
                "blocked",
                "closed",
                "not-available",
            )
            if any(marker in lowered for marker in block_markers):
                continue

            events.append(
                {
                    "platform": platform,
                    "summary": summary,
                    "start": to_date(dtstart.dt),
                    "end": to_date(dtend.dt),  # exclusive checkout date
                }
            )

    events.sort(key=lambda e: e["start"])
    return events


def make_allday_event(uid: str, summary: str, start: date, end: date, categories: str) -> Event:
    ev = Event()
    ev.add("uid", uid)
    ev.add("summary", summary)
    ev.add("dtstart", start)
    ev.add("dtend", end)
    ev.add("categories", categories)
    return ev


def make_timed_event(uid: str, summary: str, day: date, hour: int, tz, categories: str) -> Event:
    start_dt = datetime(day.year, day.month, day.day, hour, 0, tzinfo=tz)
    ev = Event()
    ev.add("uid", uid)
    ev.add("summary", summary)
    ev.add("dtstart", start_dt)
    ev.add("dtend", start_dt + timedelta(hours=EVENT_DURATION_HOURS))
    ev.add("categories", categories)
    return ev


def build_calendars(properties, tz):
    global_cal = new_calendar("Cleaning schedule - all houses")
    per_house_cals = {}
    total_events = 0

    def add_to_both(house_cal, ev):
        global_cal.add_component(ev)
        house_cal.add_component(ev)

    for prop in properties:
        name = prop["name"]
        slug = prop["slug"]
        house_cal = new_calendar(f"Cleaning schedule - {name}")

        reservations = collect_house_events(prop)

        for i, res in enumerate(reservations):
            platform = res["platform"]
            start = res["start"]
            checkout = res["end"]

            # 1) Informational all-day "stay" event.
            stay_summary = (
                f"{name} ({platform}) - {res['summary']} "
                f"({us_date(start)} - {us_date(checkout)})"
            )
            stay_uid = f"stay-{slug}-{start.isoformat()}-{platform}@cleaning-sync"
            add_to_both(
                house_cal,
                make_allday_event(stay_uid, stay_summary, start, checkout, name),
            )
            total_events += 1

            # 2) Timed CHECK-IN event at 3:00 PM.
            checkin_summary = f"{name} - CHECK-IN 3:00 PM ({platform})"
            checkin_uid = f"checkin-{slug}-{start.isoformat()}-{platform}@cleaning-sync"
            add_to_both(
                house_cal,
                make_timed_event(checkin_uid, checkin_summary, start, CHECKIN_HOUR, tz, name),
            )
            total_events += 1

            # 3) Timed CHECKOUT / CLEANING event at 11:00 AM.
            is_back_to_back = (
                i + 1 < len(reservations) and reservations[i + 1]["start"] == checkout
            )
            checkout_summary = f"{name} - CHECKOUT 11:00 AM / Cleaning ({platform})"
            if is_back_to_back:
                checkout_summary += " -- BACK-TO-BACK, next guest 3:00 PM"

            checkout_uid = f"checkout-{slug}-{checkout.isoformat()}-{platform}@cleaning-sync"
            add_to_both(
                house_cal,
                make_timed_event(checkout_uid, checkout_summary, checkout, CHECKOUT_HOUR, tz, name),
            )
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
    properties, tz = load_config()
    global_cal, per_house_cals = build_calendars(properties, tz)

    write_calendar(global_cal, DOCS_DIR / "cleaning.ics")
    for slug, cal in per_house_cals.items():
        write_calendar(cal, DOCS_DIR / f"cleaning_{slug}.ics")


if __name__ == "__main__":
    main()
