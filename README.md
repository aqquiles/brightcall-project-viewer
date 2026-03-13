# Brightcall Project Viewer + Daily Client Report

This version keeps the existing Project Viewer behavior and adds a second tab called **Daily client report**.

## What the new report does

It calls:
- `https://api.dialer.brightcall.ai/api/v1/stat/daily-projects?apiKey=...`

The endpoint returns HTML, not JSON. The app parses the HTML table, finds account-level rows by email, groups the child project rows under that account, and lets you generate a reusable report for any available client email.

## New secrets expected

Add these to `.streamlit/secrets.toml`:

```toml
BRIGHTCALL_API_KEY = "your-projects-endpoint-key"
BRIGHTCALL_DAILY_STATS_API_KEY = "your-daily-projects-endpoint-key"
DEFAULT_DAILY_REPORT_ACCOUNT = "lionrock@highlevelvoice.ai"
```

`DEFAULT_DAILY_REPORT_ACCOUNT` is optional.

## New UI structure

### Tab 1 — Project viewer
Keeps the existing project viewer workflow:
- projects endpoint
- running/not running logic
- tag fallback logic
- transfer number fallback logic
- project search
- archived filter
- grouped summary
- running-project operational view

### Tab 2 — Daily client report
Adds:
- account email selector
- manual account email input
- KPI cards for the selected account
- focused project performance table
- raw account/project tables
- downloadable CSV for the selected account
- downloadable HTML report for the selected account
- HTML preview inside Streamlit

## Parsing assumptions for the daily-projects report

The HTML parser treats a row as an **account total** row when the first cell contains an email address.
All following non-email rows are treated as project rows for that account until the next email row appears.

This is more reusable than hardcoding Lionrock.

## Files

Use:
- `streamlit_app_full.py`

This file is intended to replace or supersede the current `streamlit_app.py` once you are ready.
