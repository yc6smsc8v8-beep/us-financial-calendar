US Economic + Earnings — FRED Build (Primary Econ Source)
-------------------------------------------------
✓ ECONOMICS: FRED 'releases/dates' API with release name mapping
✓ Default times: 08:30 ET typical; 10:00 ET for JOLTS/Consumer Confidence/ISM/Factory Orders/Construction Spending
✓ Optional TE fallback (USE_TE_FALLBACK=1, TE_CRED=guest:guest)
✓ EARNINGS: FMP stable earnings with S&P500+Dow30 filter + AUTO_EXPAND_EARNINGS safety
✓ ICS: UTC + 15-min DTEND (Outlook safe), ETag/Last-Modified, /warm, /debug, /health
✓ Gunicorn: 2 workers × 2 threads, 180s timeout

Render Environment:
FRED_API_KEY=<your free FRED key>
FMP_API_KEY=<your FMP key>
LOOKAHEAD_DAYS=365
CACHE_TTL=900
INCLUDE_ALL_EARNINGS=0
AUTO_EXPAND_EARNINGS=1
USE_TE_FALLBACK=0
TE_CRED=guest:guest
