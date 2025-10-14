import os
from datetime import datetime, timedelta
import pytz
from flask import Flask, Response, jsonify
from icalendar import Calendar, Event

app = Flask(__name__)

TZ = pytz.timezone("America/New_York")

def build_calendar(events):
    from datetime import datetime
    from icalendar import Calendar, Event
    from datetime import datetime
    cal = Calendar()
    cal.add("prodid", "-//US Combined Economic & Earnings Calendar//")
    cal.add("version", "2.0")
    cal.add("X-WR-CALNAME", "US Economic & Major Earnings Calendar")
    cal.add("X-WR-TIMEZONE", "America/New_York")

    for ev in events:
        ve = Event()
        ve.add("summary", ev["summary"])
        ve.add("dtstart", ev["dt"])
        ve.add("uid", ev["uid"])
        ve.add("dtstamp", datetime.utcnow())
        if "description" in ev:
            ve.add("description", ev["description"])
        cal.add_component(ve)
    return cal.to_ical()

@app.route("/us_financial_calendar.ics")
def combined_ics():
    now = datetime.now(TZ)
    events = [
        {"summary": "GDP Release (Economic)", "dt": now + timedelta(days=1), "uid": "event1", "description": "US GDP Q3"},
        {"summary": "AAPL (AAPL) - Earnings (After Market)", "dt": now + timedelta(days=2), "uid": "event2", "description": "Apple earnings release"},
        {"summary": "CPI Release (Economic)", "dt": now + timedelta(days=3), "uid": "event3", "description": "Consumer Price Index"},
        {"summary": "MSFT (MSFT) - Earnings (Pre Market)", "dt": now + timedelta(days=4), "uid": "event4", "description": "Microsoft earnings release"}
    ]
    ics = build_calendar(events)
    return Response(ics, mimetype="text/calendar; charset=utf-8")

@app.route("/health")
def health():
    return jsonify({"status": "ok","feed_path":"/us_financial_calendar.ics"})


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
