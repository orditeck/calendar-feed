# Calendar feed

This repository builds and deploys a household collection calendar to GitHub Pages every Monday. All source-specific values are GitHub Actions secrets; the repository contains no address, building ID, schedule URL with query values, or feed path.

The deployed iCalendar contains only collection dates and generic event names. Its opaque URL is a bearer secret: anyone who learns the complete URL can download the calendar. Do not publish it.

## Required GitHub Actions secrets

- `SAGUENAY_ADDRESS`
- `SAGUENAY_BUILDING_ID`
- `CALENDAR_FEED_TOKEN`

The workflow renders the file as `site/$CALENDAR_FEED_TOKEN.ics`, then deploys it to GitHub Pages. GitHub Actions does not expose secret values to repository readers or logs.

Run the workflow manually from **Actions → Publish calendar → Run workflow**. Scheduled runs refresh the feed weekly.
