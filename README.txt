US Economic + S&P500/Dow30 Earnings — Live ICS Feed (Resilient, Outlook-safe)

- Live combined feed at /us_financial_calendar.ics
- Force refresh: /us_financial_calendar.ics?refresh=1
- Debug counts: /debug
- Outlook-safe: UTC timestamps + 15-minute DTEND
- Caching: default 15 minutes (CACHE_TTL)

Deploy on Render (Docker):
1) Push files to GitHub.
2) New Web Service → Environment: Docker → connect repo.
3) Settings → Environment → add (recommended):
   - FMP_API_KEY=<your key>
   - LOOKAHEAD_DAYS=365
   - CACHE_TTL=900
4) Manual Deploy → Deploy Latest Commit.
5) Verify: /health, /debug, /us_financial_calendar.ics
