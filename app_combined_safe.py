import os
import time
import hashlib
from datetime import datetime, timedelta
from dateutil import parser
import pytz
import requests
from flask import Flask, Response, jsonify
from icalendar import Calendar, Event

app = Flask(__name__)

# --- Config ---
FMP_API_KEY = os.getenv("FMP_API_KEY", "jGOOgPs7zXMPkcultsP6M01SrYIm15nV")
TZ = pytz.timezone("America/New_York")
UTC = pytz.utc
LOOKAHEAD_DAYS = int(os.getenv("LOOKAHEAD_DAYS", "120"))
CACHE_TTL = int(os.getenv("CACHE_TTL", "900"))
FEED_PATH = "/us_financial_calendar.ics"

# --- Cache ---
_cache = {"ics": None, "ts": 0}

# --- Universe for earnings filtering ---
DOW30 = {
    "AAPL","MSFT","JPM","V","JNJ","WMT","PG","DIS","HD","MA","XOM","PFE",
    "KO","PEP","CSCO","CVX","INTC","MCD","UNH","BAC","VZ","TRV","MMM","NKE",
    "MRK","AXP","DOW","GS","RTX","IBM"
}

FMP_BASE = "https://financialmodelingprep.com/api/v3"

def sha_uid(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest() + "@us-financial-calendar"

def utcnow():
    return datetime.utcnow().replace(tzinfo=UTC)

def to_utc(dt):
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        dt = TZ.localize(dt)
    return dt.astimezone(UTC)

# --- Fetchers (called inside request only) ---
def fetch_sp500_symbols():
    try:
        url = f"{FMP_BASE}/sp500_constituent?apikey={FMP_API_KEY}"
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        return {row.get("symbol","").upper() for row in r.json() if row.get("symbol")}
    except Exception:
        return set()

def fetch_earnings_calendar(from_date: str, to_date: str):
    try:
        url = f"{FMP_BASE}/earning_calendar"
        params = {"from": from_date, "to": to_date, "apikey": FMP_API_KEY}
        r = requests.get(url, params=params, timeout=25)
        r.raise_for_status()
        return r.json()
    except Exception:
        return []

def fetch_economic_calendar(from_date: str, to_date: str):
    try:
        url = f"{FMP_BASE}/economic_calendar"
        params = {"from": from_date, "to": to_date, "apikey": FMP_API_KEY}
        r = requests.get(url, params=params, timeout=25)
        if r.status_code != 200:
            return []
        return r.json()
    except Exception:
        return []

# --- Build ICS (Outlook-friendly: UTC, with DTEND) ---
def build_calendar(events):
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
        ve.add("dtstamp", utcnow())
        desc = ev.get("description", "")
        if desc:
            ve.add("description", desc)
        ve.add("transp", "OPAQUE")
        cal.add_component(ve)

    return cal.to_ical()

# --- Compose live events ---
def collect_combined_events():
    events = []
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

    # Earnings (S&P500 + Dow30)
    sp500 = fetch_sp500_symbols()
    universe = sp500.union(DOW30)

    earn = fetch_earnings_calendar(from_str, to_str)
    for row in earn:
        symbol = (row.get("symbol") or "").upper()
        if symbol not in universe:
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

# --- Routes ---
@app.route(FEED_PATH)
def feed():
    now = time.time()
    if _cache["ics"] and (now - _cache["ts"] < CACHE_TTL):
        return Response(_cache["ics"], mimetype="text/calendar; charset=utf-8")
    try:
        events = collect_combined_events()
        ics = build_calendar(events)
    except Exception:
        cal = Calendar()
        cal.add("prodid", "-//US Combined Economic & Earnings Calendar//")
        cal.add("version", "2.0")
        ics = cal.to_ical()
    _cache["ics"] = ics
    _cache["ts"] = now
    return Response(ics, mimetype="text/calendar; charset=utf-8")

@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "feed_path": FEED_PATH,
        "cached_seconds": CACHE_TTL
    })

@app.route("/")
def index():
    return (
        "<h3>US Economic & Earnings Calendar is running.</h3>"
        f'<p>Subscribe to the ICS feed: <a href="{FEED_PATH}">{FEED_PATH}</a></p>'
        '<p>Health check: <a href="/health">/health</a></p>'
    )

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
