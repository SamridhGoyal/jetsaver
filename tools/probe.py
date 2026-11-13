"""Read-only cloud test: open each booking site once for one route and date,
run its reader from extractors.js, and report how many flights it could read.
It writes nothing to the repository. Never solves or bypasses bot checks:
a site that shows one is reported as blocked."""
import datetime as dt, json, os, re, sys, time
from playwright.sync_api import sync_playwright

ROUTE = os.environ.get("ROUTE", "DEL-BOM")
FROM, TO = ROUTE.split("-")
CITY = {"DEL": "Delhi", "BOM": "Mumbai", "BLR": "Bengaluru"}
D = (dt.datetime.utcnow() + dt.timedelta(hours=5, minutes=30)).date() + dt.timedelta(days=2)
Y, M, DD = f"{D:%Y}", f"{D:%m}", f"{D:%d}"
ISO = D.isoformat()

SITES = [  # key, name, url, wait seconds, reader
    ("pt", "Paytm", f"https://tickets.paytm.com/flights/flightSearch/{FROM}-{CITY[FROM]}/{TO}-{CITY[TO]}/1/0/0/E/{ISO}", 9, "PAYTM"),
    ("ao", "Adani One", f"https://www.adanione.com/flight/bookingV2/srp/ADLONE/D/O/ECO/1_0_0/{FROM}-{TO}-{DD}{M}{Y}/REGF", 15, "ADANIONE"),
    ("g", "Google Flights", f"https://www.google.com/travel/flights?q=Flights%20to%20{TO}%20from%20{FROM}%20on%20{ISO}%20one%20way&curr=INR&hl=en", 8, "GOOGLE"),
    ("yv", "YovoTrip", f"https://www.yovotrip.com/flight?from={FROM}&to={TO}&startDate={ISO}&endDate=&adults=1&children=0&infants=0&class=ECONOMY&tripType=oneway", 10, "YOVOTRIP"),
    ("ix", "ixigo", f"https://www.ixigo.com/search/result/flight?from={FROM}&to={TO}&date={DD}{M}{Y}&adults=1&children=0&infants=0&class=e&source=Search%20Form", 10, "IXIGO"),
    ("emt", "EaseMyTrip", f"https://flight.easemytrip.com/FlightList/Index?srch={FROM}-{CITY[FROM]}-India|{TO}-{CITY[TO]}-India|{DD}/{M}/{Y}&px=1-0-0&cbn=0&ar=undefined&isow=true&isdm=true&lng=&", 10, "EASEMYTRIP"),
    ("ct", "Cleartrip", f"https://www.cleartrip.com/flights/results?adults=1&childs=0&infants=0&class=Economy&depart_date={DD}/{M}/{Y}&from={FROM}&to={TO}&intl=n", 10, "CLEARTRIP"),
    ("ya", "Yatra", f"https://flight.yatra.com/air-search-ui/dom2/trigger?flex=0&viewName=normal&source=fresco-flights&type=O&class=Economy&ADT=1&CHD=0&INF=0&noOfSegments=1&origin={FROM}&originCountry=IN&destination={TO}&destinationCountry=IN&flight_depart_date={DD}%2F{M}%2F{Y}&arrivalDate=&src=srpNext", 30, "YATRA"),
    ("mmt", "MakeMyTrip", f"https://www.makemytrip.com/flight/search?itinerary={FROM}-{TO}-{DD}/{M}/{Y}&tripType=O&paxType=A-1_C-0_I-0&intl=false&cabinClass=E", 14, "MMT_GI"),
    ("gi", "Goibibo", f"https://www.goibibo.com/flight/search?itinerary={FROM}-{TO}-{DD}/{M}/{Y}&tripType=O&paxType=A-1_C-0_I-0&intl=false&cabinClass=E&lang=eng", 14, "MMT_GI"),
]
BLOCK = re.compile(r"captcha|are you a robot|access denied|verify you are human|unusual traffic|request blocked|challenge validation|pardon our interruption", re.I)

src = open(os.path.join(os.path.dirname(__file__), "extractors.js"), encoding="utf-8").read()

def count(raw):
    try:
        v = json.loads(raw)
    except Exception:
        return 0, str(raw)[:80]
    rows = v["rows"] if isinstance(v, dict) else v
    return len(rows), (rows[0] if rows else None)

results = []
with sync_playwright() as p:
    browser = p.chromium.launch()
    ctx = browser.new_context(locale="en-IN", timezone_id="Asia/Kolkata", viewport={"width": 1366, "height": 900})
    page = ctx.new_page()
    for key, name, url, wait, reader in SITES:
        t0 = time.time(); status = None; note = ""
        try:
            if key == "mmt":
                page.goto("https://www.makemytrip.com/", wait_until="domcontentloaded", timeout=45000); time.sleep(4)
            resp = page.goto(url, wait_until="domcontentloaded", timeout=45000)
            status = resp.status if resp else None
            time.sleep(wait)
            if key == "pt":
                page.mouse.wheel(0, 20000); time.sleep(2)
            text = page.evaluate("() => document.body ? document.body.innerText : ''")
            raw = page.evaluate(f"() => {{ {src}\n return {reader}(); }}")
            n, first = count(raw)
            if n == 0 and BLOCK.search(text[:5000]):
                note = "blocked: bot check shown"
            elif n == 0:
                note = "no flights read: " + re.sub(r"\s+", " ", text[:160])
            results.append({"site": name, "http": status, "flights": n, "first": first, "note": note, "secs": round(time.time() - t0)})
        except Exception as e:
            results.append({"site": name, "http": status, "flights": 0, "first": None, "note": "error: " + str(e)[:160], "secs": round(time.time() - t0)})
        print(json.dumps(results[-1], ensure_ascii=False), flush=True)
    browser.close()

ok = [r["site"] for r in results if r["flights"]]
print(f"\nRoute {ROUTE} on {ISO}: {len(ok)}/{len(results)} sites returned flights from the cloud.")
print("WORKS: " + (", ".join(ok) or "none"))
print("FAILS: " + (", ".join(f"{r['site']} ({r['note'][:60]})" for r in results if not r["flights"]) or "none"))
with open(os.environ.get("GITHUB_STEP_SUMMARY", os.devnull), "a", encoding="utf-8") as f:
    f.write(f"## JetSaver cloud probe: {ROUTE} on {ISO}\n\n| Site | HTTP | Flights read | Note |\n|---|---|---|---|\n")
    for r in results:
        f.write(f"| {r['site']} | {r['http']} | {r['flights']} | {r['note'][:90].replace('|', '/')} |\n")
