US Economic + Earnings — TE Fallback Build (Full)
-------------------------------------------------
✓ AUTO_EXPAND_EARNINGS: auto include all if S&P500 list unavailable
✓ TradingEconomics fallback (USE_TE_FALLBACK=1, TE_CRED=guest:guest)
✓ Fallback marks events with "(TE fallback)" in descriptions
✓ Stable endpoints (/stable/economic-calendar, /stable/earnings-calendar) for FMP
✓ Canonical earnings times (08:00 ET Pre, 16:10 ET After); econ Time TBA→09:00 ET default
✓ ETag/Last-Modified headers, /warm, /debug (with TE probe)
✓ Gunicorn 2 workers × 2 threads, 180s timeout

Render Environment (suggested):
FMP_API_KEY=<your key>
LOOKAHEAD_DAYS=365
CACHE_TTL=900
INCLUDE_ALL_EARNINGS=0
AUTO_EXPAND_EARNINGS=1
USE_TE_FALLBACK=1
TE_CRED=guest:guest
