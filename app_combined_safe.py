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

FMP_API_KEY = "jGOOgPs7zXMPkcultsP6M01SrYIm15nV"
TZ = pytz.timezone("America/New_York")
LOOKAHEAD_DAYS = 120
CACHE_TTL = 900

_cache = {"ics": None, "ts": 0}

DOW30 = [
    "AAPL","MSFT","JPM","V","JNJ","WMT","PG","DIS","HD","MA","XOM","PFE",
    "KO","PEP","CSCO","CVX","INTC","MCD","UNH","BAC","VZ","TRV","MMM","NKE",
    "MRK","AXP","DOW","GS","RTX","IBM"
]

FMP_BASE = "https://financialmodelingprep.com/api/v3"

def make_uid(text: str) -> str:
    h = hashlib.sha1(text.encode("utf-8")).hexdigest()
    return f"{h}@combined-econ-earnings.local"

def utcnow():
    return datetime.utcnow().replace(tzinfo=pytz.utc)

def fetch_sp500_symbols():
    try:
        url = f"{FMP_BASE}/sp500_constituent?apikey={FMP_API_KEY}"
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        data = r.json()
        return [item.get("symbol") for item in data if item.get("symbol")]
    except Exception:
        return []

def fetch_earnings_calendar(from_date: str, to_date: str):
    try:
        url = f"{FMP_BASE}/earning_calendar"
        params = {"from": from_date, "to": to_date, "apikey": FMP_API_KEY}
        r = requests.get(url, params=params, timeout=20)
        r.raise_for_status()
        return r.json()
    except Exception:
        return []

def fetch_economic_calendar(from_date: str, to_date: str):
    try:
        url = f"{FMP_BASE}/economic_calendar"
        params = {"from": from_date, "to": to_date, "apikey": FMP_API_KEY}
        r = requests.get(url, params=params, timeout=20)
        r.raise_for_status()
        return r.json()
    except Exception:
        return []

def build_calendar(events):
    cal = Calendar()
    cal.add("prodid", "-//US Combined Economic & Earnings Calendar//")
    cal.add("version", "2.0")
    cal.add("X-WR-CALNAME", "US Economic & Major Earnings Calendar")
    cal.add("X-WR-TIMEZONE", "America/New_York")

    for ev in events:
        summary = ev.get("summary")
        dt = ev.get("dt")
        uid_text = ev.get("uid_text")
        description = ev.get("description", "")
        if not summary or not dt:
            continue
        ve = Event()
        ve.add("summary", summary)
        ve.add("dtstart", dt)
        ve.add("uid", make_uid(uid_text or f"{summary}-{dt.isoformat()}"))
        ve.add("dtstamp", utcnow())
        if description:
            ve.add("description", description)
        cal.add_component(ve)
    return cal.to_ical()

def collect_combined_events():
    events = []
    today = datetime.now(TZ).date()
    to_date = today + timedelta(days=LOOKAHEAD_DAYS)
    from_str = today.isoformat()
    to_str = to_date.isoformat()

    econ_raw = fetch_economic_calendar(from_str, to_str)
    for item in econ_raw:
        country = (item.get("country") or "").upper()
        if country not in ("US", "USA", "UNITED STATES"):
            continue
        name = item.get("event") or item.get("name") or item.get("title")
        date_raw = item.get("date") or ""
        if not name or not date_raw:
            continue
        try:
            dt = parser.parse(date_raw)
            if dt.tzinfo is None:
                dt = TZ.localize(dt)
        except:
            continue
        events.append({
            "summary": f"{name} (Economic)",
            "dt": dt,
            "uid_text": f"econ-{name}-{dt.isoformat()}",
            "description": "Economic release"
        })

    sp500_symbols = fetch_sp500_symbols()
    symbol_set = set(sp500_symbols)
    symbol_set.update(DOW30)

    earnings_raw = fetch_earnings_calendar(from_str, to_str)
    for ev in earnings_raw:
        symbol = (ev.get("symbol") or "").upper()
        if symbol not in symbol_set:
            continue
        company = ev.get("company") or ev.get("companyName") or symbol
        date_raw = ev.get("date")
        time_info = (ev.get("time") or "").strip()
        if not date_raw:
            continue
        try:
            dt = parser.parse(date_raw)
            if dt.tzinfo is None:
                dt = TZ.localize(dt)
        except:
            continue
        timing_label = ""
        t_low = time_info.lower()
        if "before" in t_low or "pre" in t_low or "am" in t_low:
            timing_label = " (Pre Market)"
        elif "after" in t_low or "pm" in t_low or "bmo" in t_low or "after market" in t_low:
            timing_label = " (After Market)"
        events.append({
            "summary": f"{company} ({symbol}) - Earnings{timing_label}",
            "dt": dt,
            "uid_text": f"earn-{symbol}-{dt.isoformat()}",
            "description": f"Earnings: {symbol} {time_info}"
        })

    return sorted(events, key=lambda x: x["dt"])

@app.route("/us_financial_calendar.ics")
def combined_ics():
    now = time.time()
    if _cache["ics"] and (now - _cache["ts"] < CACHE_TTL):
        return Response(_cache["ics"], mimetype="text/calendar; charset=utf-8")
    events = collect_combined_events()
    ics = build_calendar(events)
    _cache["ics"] = ics
    _cache["ts"] = now
    return Response(ics, mimetype="text/calendar; charset=utf-8")

@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "feed_path": "/us_financial_calendar.ics",
        "cached_seconds": CACHE_TTL
    })

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
