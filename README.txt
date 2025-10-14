US Economic + S&P500/Dow30 Earnings — Live ICS (Chunked, Resilient, Outlook-safe)

- Feed: /us_financial_calendar.ics  (add ?refresh=1 to bypass cache)
- Debug: /debug  (shows raw counts & window)
- Test toggle: ?all=1 includes all earnings symbols
- Outlook-safe: UTC timestamps + 15-min DTEND
- Chunked API fetch (60-day windows) to avoid provider caps

Deploy on Render (Docker):
1) Push these three files to GitHub.
2) Render → New Web Service → Environment: Docker → connect repo.
3) Settings → Environment (recommended):
   - FMP_API_KEY=<your key>
   - LOOKAHEAD_DAYS=365
   - CACHE_TTL=300  (while testing; raise later)
   - INCLUDE_ALL_EARNINGS=1  (test only; remove/0 later)
4) Manual Deploy → Deploy Latest Commit.
5) Verify /debug and /us_financial_calendar.ics?refresh=1.
