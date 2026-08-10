"""Backtest without lookahead bias — point-in-time (vintage) history.

Sources restate numbers after first publication. A backtest that reads
today's data sees revisions that did not exist at decision time, and
quietly overstates its own performance.

Add `as_of` to any history endpoint and the API returns the series as it
was knowable at that instant: rows collected later are absent, and values
revised later are rolled back to what was published at the time.

Real example: on 7 August 2026 the US diesel price for that day was
published as 3.88, then revised to 3.90 at 22:10 UTC. A backtest deciding
at 22:00 must see 3.88 — and with as_of, it does.

    OILPRICEAPI_KEY=... python 02_backtest_without_lookahead.py

Requires a paid key (Developer, $19/mo and up).
"""

import os

import requests

API = "https://api.oilpriceapi.com/v1/prices/past_week"
KEY = os.environ.get("OILPRICEAPI_KEY")
if not KEY:
    raise SystemExit("Set OILPRICEAPI_KEY — free key at https://oilpriceapi.com/auth/signup")
HEADERS = {"Authorization": f"Token {KEY}"}
PARAMS = {"by_code": "DIESEL_USD", "per_page": 3}

# The world as it was knowable on 7 Aug 2026 at 22:00 UTC
resp = requests.get(
    API, headers=HEADERS, timeout=10,
    params={**PARAMS, "as_of": "2026-08-07T22:00:00Z"},
)
resp.raise_for_status()
vintage = resp.json()["data"]["prices"]

# The world as it is known today (revisions applied)
resp = requests.get(
    API, headers=HEADERS, timeout=10,
    params={**PARAMS, "start_date": "2026-08-07", "end_date": "2026-08-08"},
)
resp.raise_for_status()
current = resp.json()["data"]["prices"]

print("as-of 2026-08-07 22:00 UTC (what a backtest may see):")
for p in vintage:
    print(f"  {p['created_at'][:16]}  ${p['price']}")

print("\nsame rows as known today (revisions applied):")
for p in current[: len(vintage)]:
    print(f"  {p['created_at'][:16]}  ${p['price']}")

# Response headers tell you the vintage contract:
#   X-Vintage-As-Of: the instant you asked for
#   X-Vintage-Revision-Coverage-Since: revisions are rolled back from this
#     date forward (2026-07-28); values before a series' collection start
#     have no vintages, by construction.
