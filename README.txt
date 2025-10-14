US Economic + Earnings — Auto-Expand Notifier Build
-------------------------------------------------
✓ AUTO_EXPAND_EARNINGS: if S&P500 list is unavailable, filter auto-expands to all earnings
✓ Each earnings VEVENT DESCRIPTION includes a note when auto-expanded:
  "Note: Auto-expanded — S&P500 list unavailable at build time"
✓ INCLUDE_ALL_EARNINGS=0 keeps S&P500+Dow30 when possible
✓ Stable endpoints (/stable/economic-calendar, /stable/earnings-calendar)
✓ Canonical times (08:00 ET Pre, 16:10 ET After); econ Time TBA→09:00 ET
✓ ETag/Last-Modified headers, /warm, /debug
✓ Gunicorn 2 workers × 2 threads, 180s timeout
