
import os
import time
import hashlib
from typing import List
from datetime import datetime, timedelta
from dateutil import parser
import pytz
import requests
from flask import Flask, Response, jsonify, request
from icalendar import Calendar, Event

app = Flask(__name__)

# =====================
# Config (env-overridable)
# =====================
FMP_API_KEY = os.getenv("FMP_API_KEY", "demo")  # <-- set your real key in Render env
TZ = pytz.timezone("America/New_York")
LOOKAHEAD_DAYS = int(os.getenv("LOOKAHEAD_DAYS", "365"))
CACHE_TTL = int(os.getenv("CACHE_TTL", "600"))
FEED_PATH = "/us_financial_calendar.ics"
INCLUDE_ALL_EARNINGS_ENV = os.getenv("INCLUDE_ALL_EARNINGS", "0") == "1"

# Endpoints (FMP stable for econ & earnings)
FMP_STABLE_BASE = "https://financialmodelingprep.com/stable"
FMP_V3_BASE = "https://financialmodelingprep.com/api/v3"  # for S&P500 list
UA = {"User-Agent": "US-Financial-ICS/1.2"}

# In-memory cache
_cache = {"ics": None, "ts": 0}

# Universe seed (Dow 30)
DOW30 = {
    "AAPL","MSFT","JPM","V","JNJ","WMT","PG","DIS","HD","MA","XOM","PFE",
    "KO","PEP","CSCO","CVX","INTC","MCD","UNH","BAC","VZ","TRV","MMM","NKE",
    "MRK","AXP","DOW","GS","RTX","IBM"
}

# =====================
# Helpers
# =====================
def sha_uid(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest() + "@us-financial-calendar"

def to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        dt = TZ.localize(dt)
    return dt.astimezone(pytz.utc)

def _get(url, **kwargs):
    # simple retry wrapper
    for i in range(3):
        try:
            r = requests.get(url, headers=UA, timeout=25, **kwargs)
            if r.status_code == 200:
                return r
        except Exception:
            if i == 2:
                raise
        time.sleep(0.8 * (i + 1))
    return None

def daterange_chunks(start_date: datetime, end_date: datetime, step_days: int = 60):
    cur = start_date
    while cur <= end_date:
        nxt = min(cur + timedelta(days=step_days-1), end_date)
        yield cur, nxt
        cur = nxt + timedelta(days=1)

# =====================
# Fetchers (chunked)
# =====================
def fetch_sp500_symbols() -> set:
    try:
        r = _get(f"{FMP_V3_BASE}/sp500_constituent", params={"apikey": FMP_API_KEY})
        if r:
            return {row.get("symbol","").upper() for row in r.json() if row.get("symbol")}
    except Exception:
        pass
    return set()

def fetch_earnings_calendar(from_date: str, to_date: str) -> List[dict]:
    results = []
    start = datetime.fromisoformat(from_date)
    end = datetime.fromisoformat(to_date)
    for s, e in daterange_chunks(start, end, step_days=60):
        try:
            r = _get(f"{FMP_STABLE_BASE}/earnings-calendar",
                     params={"from": s.date().isoformat(), "to": e.date().isoformat(), "apikey": FMP_API_KEY})
            if r:
                data = r.json()
                if isinstance(data, list):
                    results.extend(data)
        except Exception:
            continue
    return results

def fetch_economic_calendar(from_date: str, to_date: str) -> List[dict]:
    results = []
    start = datetime.fromisoformat(from_date)
    end = datetime.fromisoformat(to_date)
    for s, e in daterange_chunks(start, end, step_days=60):
        try:
            r = _get(f"{FMP_STABLE_BASE}/economic-calendar",
                     params={"from": s.date().isoformat(), "to": e.date().isoformat(), "apikey": FMP_API_KEY})
            if r:
                data = r.json()
                if isinstance(data, list):
                    results.extend(data)
        except Exception:
            continue
    return results

# =====================
# ICS builder (UTC + DTEND for Outlook)
# =====================
def build_calendar(events: List[dict]) -> bytes:
    cal = Calendar()
    cal.add("prodid", "-//US Combined Economic & Earnings Calendar//")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    cal.add("X-WR-CALNAME", "US Economic & Major Earnings Calendar")
    cal.add("X-WR-TIMEZONE", "America/New_York")

    for ev in events:
        dtstart_utc = to_utc(ev["dt"])
        dtend_utc = dtstart_utc + timedelta(minutes=15)

        ve = Event()
        ve.add("summary", ev["summary"])
        ve.add("dtstart", dtstart_utc)
        ve.add("dtend", dtend_utc)
        ve.add("uid", sha_uid(ev.get("uid_text") or f'{ev["summary"]}-{dtstart_utc.isoformat()}'))
        ve.add("dtstamp", to_utc(datetime.utcnow()))
        if ev.get("description"):
            ve.add("description", ev["description"])
        ve.add("transp", "OPAQUE")
        cal.add_component(ve)

    return cal.to_ical()

# =====================
# Compose live events
# =====================
def collect_combined_events() -> List[dict]:
    events: List[dict] = []
    today = datetime.now(TZ).date()
    to_date = today + timedelta(days=LOOKAHEAD_DAYS)
    from_str, to_str = today.isoformat(), to_date.isoformat()

    # Economic (US only)
    econ = fetch_economic_calendar(from_str, to_str)
    for item in econ:
        country = (item.get("country") or item.get("countryCode") or "").upper()
        if country not in {"US", "USA", "UNITED STATES", "UNITED STATES OF AMERICA"}:
            continue
        name = item.get("event") or item.get("name") or item.get("title")
        date_raw = item.get("date") or item.get("datetime") or item.get("date_time")
        time_raw = item.get("time")
        if not name or not date_raw:
            continue
        try:
            dt_local = parser.parse(f"{date_raw} {time_raw}" if time_raw else date_raw)
        except Exception:
            continue
        events.append({
            "summary": f"{name} (Economic)",
            "dt": dt_local,
            "uid_text": f"econ::{name}::{date_raw}::{time_raw or ''}",
            "description": "Economic release",
        })

    # Earnings (S&P500 + Dow30 by default; include all if toggled)
    sp500 = fetch_sp500_symbols()
    universe = sp500.union(DOW30) if sp500 else set(DOW30)

    earn = fetch_earnings_calendar(from_str, to_str)
    include_all = INCLUDE_ALL_EARNINGS_ENV
    try:
        if request.args.get("all") == "1":
            include_all = True
    except Exception:
        pass

    for row in earn:
        symbol = (row.get("symbol") or "").upper()
        if not include_all and symbol not in universe:
            continue
        company = row.get("company") or row.get("companyName") or symbol
        date_raw = row.get("date")
        when = (row.get("time") or row.get("hour") or row.get("when") or "").strip()
        if not date_raw:
            continue
        try:
            dt_local = parser.parse(date_raw)
        except Exception:
            continue

        label = ""
        w = when.lower()
        if any(k in w for k in ["before", "pre", "bmo", "am"]):
            label = " (Pre Market)"
        elif any(k in w for k in ["after", "post", "pm", "after market", "amc"]):
            label = " (After Market)"

        events.append({
            "summary": f"{company} ({symbol}) - Earnings{label}",
            "dt": dt_local,
            "uid_text": f"earn::{symbol}::{date_raw}::{when}",
            "description": f"Earnings: {symbol} {when}",
        })

    events.sort(key=lambda e: to_utc(e["dt"]))
    return events

# =====================
# Routes
# =====================
@app.route(FEED_PATH)
def feed():
    force = request.args.get("refresh") == "1"
    now = time.time()

    if _cache["ics"] and not force and (now - _cache["ts"] < CACHE_TTL):
        return Response(_cache["ics"], mimetype="text/calendar; charset=utf-8")

    try:
        events = collect_combined_events()
        if not events:
            # Fallback snapshot so subscribers always see something
            tznow = datetime.now(TZ)
            events = [
                {"summary": "Fallback GDP (Economic)", "dt": tznow + timedelta(days=1), "uid_text": "fallback-econ-1", "description": "Temporary fallback"},
                {"summary": "Fallback Earnings (AAPL) - After Market", "dt": tznow + timedelta(days=2), "uid_text": "fallback-earn-1", "description": "Temporary fallback"},
            ]
        ics = build_calendar(events)
    except Exception:
        cal = Calendar()
        cal.add("prodid", "-//US Combined Economic & Earnings Calendar//")
        cal.add("version", "2.0")
        ics = cal.to_ical()

    _cache["ics"] = ics
    _cache["ts"] = now
    return Response(ics, mimetype="text/calendar; charset=utf-8")

@app.route("/debug")
def debug():
    try:
        today = datetime.now(TZ).date()
        to_date = today + timedelta(days=LOOKAHEAD_DAYS)
        from_str, to_str = today.isoformat(), to_date.isoformat()

        sp = _get(f"{FMP_V3_BASE}/sp500_constituent", params={"apikey": FMP_API_KEY})
        er = _get(f"{FMP_STABLE_BASE}/earnings-calendar", params={"from": from_str, "to": to_str, "apikey": FMP_API_KEY})
        ec = _get(f"{FMP_STABLE_BASE}/economic-calendar", params={"from": from_str, "to": to_str, "apikey": FMP_API_KEY})

        def size(resp):
            try:
                data = resp.json()
                return len(data) if isinstance(data, list) else 1
            except Exception:
                return -1

        return jsonify({
            "status": "ok",
            "window": {"from": from_str, "to": to_str},
            "sp500_status": None if not sp else sp.status_code,
            "sp500_size": None if not sp else size(sp),
            "earnings_status": None if not er else er.status_code,
            "earnings_size": None if not er else size(er),
            "economics_status": None if not ec else ec.status_code,
            "economics_size": None if not ec else size(ec),
            "include_all_earnings": INCLUDE_ALL_EARNINGS_ENV,
            "using_key_prefix": (FMP_API_KEY[:4] + "***") if FMP_API_KEY else None
        })
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500

@app.route("/health")
def health():
    return jsonify({"status": "ok", "feed_path": FEED_PATH, "cached_seconds": CACHE_TTL})

@app.route("/")
def index():
    return (
        "<h3>US Economic & Earnings Calendar is running (stable endpoints).</h3>"
        f'<p>Subscribe to the ICS feed: <a href="{FEED_PATH}">{FEED_PATH}</a></p>'
        '<p>Health: <a href="/health">/health</a> | Debug: <a href="/debug">/debug</a></p>'
        '<p>Force refresh: <a href="/us_financial_calendar.ics?refresh=1">/us_financial_calendar.ics?refresh=1</a></p>'
        '<p>Include all earnings (test): append <code>&all=1</code> to the feed URL.</p>'
    )

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
