# Cleaning Calendar Sync — Airbnb + Vrbo, 5 Houses

Automatically merges the **Airbnb and Vrbo** calendars of your 5 houses,
organized by house, into one or more links your cleaning team only needs
to add once. Updates itself automatically, every hour, no paid third-party
app required.

## How it works

```
Airbnb House 1 ─┐
Vrbo    House 1 ─┤
Airbnb House 2 ─┤
Vrbo    House 2 ─┤
   ...           ┼──► merge_ical.py ──► docs/cleaning.ics (all houses)
Airbnb House 5 ─┤                  └──► docs/cleaning_house-1.ics (per house)
Vrbo    House 5 ─┘                  └──► docs/cleaning_house-2.ics
                          ▲                     ... etc
                   re-run every hour
                   by GitHub Actions (free)
```

Every event is labeled with the house, the platform, and the date range
in US format (MM/DD/YYYY), e.g.:

```
House 3 (Vrbo) - Reserved (07/10/2026 - 07/13/2026)
```

You can hand the cleaning team the combined file (`cleaning.ics`) to see
everything at once, or a single house's file if some team members only
handle one property.

## Step 1 — Get your iCal links (Airbnb + Vrbo, per house)

**Airbnb**, for each listing:
1. Listing → **Calendar** → **Availability**
2. **Export calendar** (or **Sync calendar**)
3. Copy the link (`https://www.airbnb.com/calendar/ical/....ics?s=...`)

**Vrbo**, for each listing:
1. Vrbo extranet → your property → **Calendar**
2. **Calendar sync** → **Export**
3. Copy the iCal link

## Step 2 — Fill in `config.json`

Open `config.json`. For each house, replace:
- `name`: a clear house name (shown in event titles)
- `slug`: a simple id with no spaces (used in the file name, e.g.
  `cleaning_house-1.ics`)
- both `ical_url` values (Airbnb and Vrbo) with your real links

## Step 3 — Create a GitHub repo (free)

1. Sign up at [github.com](https://github.com) if needed
2. **New repository**, e.g. `cleaning-calendar`
   - A **public** repo is the simplest way to get GitHub Pages working
     for free. The .ics file URL isn't indexed by search engines and no
     one will guess it unless you share it yourself — but keep that in
     mind if your booking dates are sensitive.
3. Upload all the files from this project into the repo (via the web
   interface, or `git push` from the command line)

## Step 4 — Enable GitHub Pages

1. **Settings** → **Pages**
2. Source: **Deploy from a branch**
3. Branch: `main`, folder: `/docs`
4. Save. You'll get a URL like:
   `https://YOUR_USERNAME.github.io/cleaning-calendar/cleaning.ics`
   and `https://YOUR_USERNAME.github.io/cleaning-calendar/cleaning_house-1.ics`, etc.

## Step 5 — Run it once

Go to the **Actions** tab → **Sync cleaning calendar** workflow →
**Run workflow**. After that, it re-runs automatically every hour on
its own.

## Step 6 — Share the link(s) with the cleaning team

- **Google Calendar**: Other calendars → `+` → From URL
- **Apple Calendar**: File → New Calendar Subscription
- **Outlook**: Add calendar → Subscribe from web

Once subscribed, their app refreshes on its own (usually every few
hours, depending on the app).

## Test locally (optional)

```bash
pip install -r requirements.txt
python3 merge_ical.py
```

## Notes

- Everything is free: GitHub (repo + Actions + Pages) costs nothing for
  this kind of usage.
- The `docs/*.ics` files are regenerated on every run.
- To add/remove a house or a platform later, just edit `config.json`.
