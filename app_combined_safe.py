
import os
import time
import hashlib
from typing import List, Dict
from datetime import datetime, timedelta
from dateutil import parser
import pytz
import requests
from flask import Flask, Response, jsonify, request, make_response
from icalendar import Calendar, Event

app = Flask(__name__)

# ===== Config (env) =====
FMP_API_KEY = os.getenv("FMP_API_KEY", "demo")  # set your real key in Render
FRED_API_KEY = os.getenv("FRED_API_KEY", "")    # REQUIRED for FRED econ
TZ = pytz.timezone("America/New_York")
LOOKAHEAD_DAYS = int(os.getenv("LOOKAHEAD_DAYS", "365"))
CACHE_TTL = int(os.getenv("CACHE_TTL", "900"))
FEED_PATH = "/us_financial_calendar.ics"

INCLUDE_ALL_EARNINGS_ENV = os.getenv("INCLUDE_ALL_EARNINGS", "0") == "1"
AUTO_EXPAND_EARNINGS = os.getenv("AUTO_EXPAND_EARNINGS", "1") == "1"  # default ON
USE_TE_FALLBACK = os.getenv("USE_TE_FALLBACK", "0") == "1"            # optional extra fallback
TE_CRED = os.getenv("TE_CRED", "guest:guest")

# Endpoints
FMP_STABLE_BASE = "https://financialmodelingprep.com/stable"
FMP_V3_BASE = "https://financialmodelingprep.com/api/v3"  # S&P500 list
FRED_BASE = "https://api.stlouisfed.org/fred"
TE_BASE = "https://api.tradingeconomics.com"
UA = {"User-Agent": "US-Financial-ICS/1.7"}

# Cache
_cache = {"ics": None, "ts": 0}

# Dow 30 seed
DOW30 = {
    "AAPL","MSFT","JPM","V","JNJ","WMT","PG","DIS","HD","MA","XOM","PFE",
    "KO","PEP","CSCO","CVX","INTC","MCD","UNH","BAC","VZ","TRV","MMM","NKE",
    "MRK","AXP","DOW","GS","RTX","IBM"
}

# ===== Helpers =====
def sha_uid(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest() + "@us-financial-calendar"

def to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        dt = TZ.localize(dt)
    return dt.astimezone(pytz.utc)

def _get(url, **kwargs):
    for i in range(3):
        try:
            r = requests.get(url, headers=UA, timeout=25, **kwargs)
            if r.status_code == 200:
                return r
        except Exception:
            if i == 2:
                raise
        time.sleep(0.7 * (i + 1))
    return None

def daterange_chunks(start_date: datetime, end_date: datetime, step_days: int = 60):
    cur = start_date
    while cur <= end_date:
        nxt = min(cur + timedelta(days=step_days-1), end_date)
        yield cur, nxt
        cur = nxt + timedelta(days=1)

# ===== FRED (economics) =====
def fetch_fred_release_map() -> Dict[int, str]:
    # Map release_id -> release_name
    r = _get(f"{FRED_BASE}/releases", params={"api_key": FRED_API_KEY, "file_type": "json"})
    if not r:
        return {}
    data = r.json() or {}
    rels = data.get("releases", [])
    out = {}
    for rel in rels:
        rid = rel.get("id") or rel.get("release_id")
        name = rel.get("name") or rel.get("release_name")
        if rid is not None and name:
            out[int(rid)] = name
    return out

def fetch_economic_calendar_fred(from_date: str, to_date: str) -> List[dict]:
    # Use FRED releases/dates, then map to names via releases list
    results = []
    r = _get(f"{FRED_BASE}/releases/dates", params={
        "api_key": FRED_API_KEY,
        "file_type": "json",
        "include_release_dates_with_no_data": "true",
        "realtime_start": from_date,
        "realtime_end": to_date
    })
    if not r:
        return results
    data = r.json() or {}
    dates = data.get("release_dates", [])
    if not dates:
        return results

    id_to_name = fetch_fred_release_map()

    for d in dates:
        date_str = d.get("date")
        rid = d.get("release_id") or d.get("id")
        if not date_str or rid is None:
            continue
        rid = int(rid)
        name = d.get("release_name") or id_to_name.get(rid) or "Economic Release"
        results.append({"event": name, "date": date_str, "time": None, "country": "US"})
    return results

# ===== TE fallback (optional) =====
def fetch_economic_calendar_te(from_date: str, to_date: str) -> List[dict]:
    results = []
    start = datetime.fromisoformat(from_date)
    end = datetime.fromisoformat(to_date)
    for s, e in daterange_chunks(start, end, step_days=60):
        r = _get(f"{TE_BASE}/calendar/country/united states",
                 params={"d1": s.date().isoformat(), "d2": e.date().isoformat(), "c": TE_CRED, "format": "json"})
        if r:
            data = r.json()
            if isinstance(data, list):
                for item in data:
                    if (item.get("Country") or "").lower() != "united states":
                        continue
                    name = item.get("Event") or item.get("Category") or "Economic Event"
                    dt_str = item.get("Date") or item.get("DateUtc") or item.get("date")
                    if not name or not dt_str:
                        continue
                    results.append({"event": name, "date": dt_str, "time": None, "country": "US", "_te": True})
    return results

# ===== Earnings (FMP) =====
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

# ===== ICS =====
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

# ===== Compose live events =====
def collect_combined_events() -> List[dict]:
    events: List[dict] = []
    today = datetime.now(TZ).date()
    to_date = today + timedelta(days=LOOKAHEAD_DAYS)
    from_str, to_str = today.isoformat(), to_date.isoformat()

    # Economics via FRED (primary)
    econ = []
    if FRED_API_KEY:
        econ = fetch_economic_calendar_fred(from_str, to_str)

    # Optional TE fallback
    used_te = False
    if not econ and USE_TE_FALLBACK:
        te = fetch_economic_calendar_te(from_str, to_str)
        econ.extend(te)
        used_te = len(te) > 0

    ten_am_keywords = ["Job Openings", "JOLTS", "Consumer Confidence", "ISM", "Factory Orders", "Construction Spending"]
    for item in econ:
        name = item.get("event") or "Economic Release"
        date_raw = item.get("date")
        if not date_raw:
            continue
        default_time = "08:30"
        for kw in ten_am_keywords:
            if kw.lower() in name.lower():
                default_time = "10:00"
                break
        if "T" in str(date_raw) and len(str(date_raw)) > 10:
            dt_local = parser.parse(date_raw)
        else:
            dt_local = TZ.localize(datetime.combine(parser.parse(date_raw).date(),
                                                    datetime.strptime(default_time, "%H:%M").time()))
        desc = "Economic release (FRED releases/dates)" if not used_te else "Economic release (TE fallback)"
        events.append({
            "summary": f"{name} (Economic)",
            "dt": dt_local,
            "uid_text": f"econ::{name}::{date_raw}",
            "description": desc
        })

    # Earnings
    sp500 = fetch_sp500_symbols()
    universe = sp500.union(DOW30) if sp500 else set(DOW30)
    earn = fetch_earnings_calendar(from_str, to_str)

    include_all = INCLUDE_ALL_EARNINGS_ENV
    auto_expanded_now = False
    if not include_all and AUTO_EXPAND_EARNINGS and len(sp500) == 0:
        include_all = True
        auto_expanded_now = True

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
        default_et = None
        w = when.lower()
        if any(k in w for k in ["before", "pre", "bmo", "am"]):
            label = " (Pre Market)"
            default_et = datetime.combine(dt_local.date(), datetime.strptime("08:00","%H:%M").time())
        elif any(k in w for k in ["after", "post", "pm", "after market", "amc"]):
            label = " (After Market)"
            default_et = datetime.combine(dt_local.date(), datetime.strptime("16:10","%H:%M").time())
        if default_et:
            dt_local = TZ.localize(default_et)

        desc = f"Earnings: {symbol} {when}".strip()
        if auto_expanded_now and not INCLUDE_ALL_EARNINGS_ENV:
            desc += "\nNote: Auto-expanded — S&P500 list unavailable at build time"

        events.append({
            "summary": f"{company} ({symbol}) - Earnings{label}",
            "dt": dt_local,
            "uid_text": f"earn::{symbol}::{date_raw}",
            "description": desc,
        })

    events.sort(key=lambda e: to_utc(e["dt"]))
    return events

# ===== Routes =====
@app.route(FEED_PATH)
def feed():
    force = request.args.get("refresh") == "1"
    now = time.time()
    if _cache["ics"] and not force and (now - _cache["ts"] < CACHE_TTL):
        ics = _cache["ics"]
    else:
        events = collect_combined_events()
        if not events:
            tznow = datetime.now(TZ)
            events = [{"summary": "Fallback GDP (Economic)", "dt": tznow + timedelta(days=1)}]
        ics = build_calendar(events)
        _cache["ics"] = ics
        _cache["ts"] = now

    resp = make_response(ics)
    resp.mimetype = "text/calendar; charset=utf-8"
    etag = hashlib.sha1(ics).hexdigest()
    resp.headers["ETag"] = etag
    resp.headers["Last-Modified"] = time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime())
    return resp

@app.route("/warm")
def warm():
    try:
        events = collect_combined_events()
        ics = build_calendar(events)
        _cache["ics"] = ics
        _cache["ts"] = time.time()
        return jsonify({"status": "ok", "events": len(events)})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500

@app.route("/debug")
def debug():
    try:
        today = datetime.now(TZ).date()
        to_date = today + timedelta(days=LOOKAHEAD_DAYS)
        from_str, to_str = today.isoformat(), to_date.isoformat()

        sp = _get(f"{FMP_V3_BASE}/sp500_constituent", params={"apikey": FMP_API_KEY})
        er = _get(f"{FMP_STABLE_BASE}/earnings-calendar", params={"from": from_str, "to": to_str, "apikey": FMP_API_KEY})
        fred_dates = _get(f"{FRED_BASE}/releases/dates", params={
            "api_key": FRED_API_KEY, "file_type": "json",
            "include_release_dates_with_no_data": "true",
            "realtime_start": from_str, "realtime_end": to_str
        }) if FRED_API_KEY else None

        def size(resp):
            try:
                data = resp.json()
                if isinstance(data, dict) and "release_dates" in data:
                    return len(data.get("release_dates", []))
                return len(data) if isinstance(data, list) else 1
            except Exception:
                return -1

        sp_size = None if not sp else size(sp)

        te_probe = None
        if USE_TE_FALLBACK:
            t = _get(f"{TE_BASE}/calendar/country/united states", params={"d1": from_str, "d2": to_str, "c": TE_CRED, "format": "json"})
            te_probe = {"status": None if not t else t.status_code, "size": None if not t else size(t)}

        return jsonify({
            "status": "ok",
            "window": {"from": from_str, "to": to_str},
            "sp500_status": None if not sp else sp.status_code,
            "sp500_size": sp_size,
            "earnings_status": None if not er else er.status_code,
            "earnings_size": None if not er else size(er),
            "fred_status": None if not fred_dates else fred_dates.status_code,
            "fred_size": None if not fred_dates else size(fred_dates),
            "te_fallback_enabled": USE_TE_FALLBACK,
            "te_probe": te_probe,
            "include_all_earnings": INCLUDE_ALL_EARNINGS_ENV,
            "auto_expand_enabled": AUTO_EXPAND_EARNINGS,
            "auto_expanded_now": (not INCLUDE_ALL_EARNINGS_ENV and AUTO_EXPAND_EARNINGS and (sp_size in (None, 0))),
        })
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500

@app.route("/health")
def health():
    return jsonify({"status": "ok", "feed_path": FEED_PATH, "cached_seconds": CACHE_TTL})

@app.route("/")
def index():
    return (
        "<h3>US Economic & Earnings Calendar is running (FRED econ).</h3>"
        f'<p>Subscribe: <a href="{FEED_PATH}">{FEED_PATH}</a></p>'
        '<p>Health: <a href="/health">/health</a> | Debug: <a href="/debug">/debug</a></p>'
        '<p>Warm cache: <a href="/warm">/warm</a> | Refresh ICS: <a href="/us_financial_calendar.ics?refresh=1">feed</a></p>'
    )

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
