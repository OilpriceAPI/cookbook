"""Pull decades of history with arbitrary date ranges.

The by_period filter takes Unix timestamps, so you are not limited to the
named windows (past_day/week/month/year). Henry Hub natural gas runs back
to 1997 — this pulls December 1997, when gas traded around $2.27/MMBtu.

    OILPRICEAPI_KEY=... python 05_deep_history_1997.py

Requires a paid key (Developer, $19/mo and up).
"""

import datetime as dt
import os

import requests

KEY = os.environ.get("OILPRICEAPI_KEY")
if not KEY:
    raise SystemExit("Set OILPRICEAPI_KEY — free key at https://oilpriceapi.com/auth/signup")

start = int(dt.datetime(1997, 12, 1, tzinfo=dt.timezone.utc).timestamp())
end = int(dt.datetime(1998, 1, 1, tzinfo=dt.timezone.utc).timestamp())

resp = requests.get(
    "https://api.oilpriceapi.com/v1/prices",
    headers={"Authorization": f"Token {KEY}"},
    params={
        "by_code": "NATURAL_GAS_USD",
        "by_period[from]": start,
        "by_period[to]": end,
        "per_page": 5,
    },
    timeout=15,
)
resp.raise_for_status()

for p in resp.json()["data"]["prices"]:
    print(f"{p['created_at'][:10]}  ${p['price']}/MMBtu  ({p['source']})")

# Windows over 30 days are automatically downsampled to keep responses
# fast; narrow the range or page through for full resolution.
