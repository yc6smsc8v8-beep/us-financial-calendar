US Economic + Earnings — Live ICS (Latest build)
- Uses FMP **stable** endpoints for economic & earnings calendars.
- Chunked API calls (60-day windows), retries, and server caching.
- Outlook-safe ICS (UTC + 15-min DTEND).
- Debug endpoint `/debug` shows HTTP status and list sizes.
- Cache-bypass: append `?refresh=1` to the feed URL.
- Earnings filter: S&P 500 + Dow30 by default; set env `INCLUDE_ALL_EARNINGS=1` or use `&all=1` to include all.

Render → Settings → Environment:
- FMP_API_KEY=<your key with stable endpoint access>
- LOOKAHEAD_DAYS=365
- CACHE_TTL=600
- INCLUDE_ALL_EARNINGS=1   # (optional for testing)

Feed URL:   /us_financial_calendar.ics
Health:     /health
Debug:      /debug
