"""Your whole watchlist in one request — batch, pandas, CSV.

The naive loop asks six times for what one request answers. Polling six codes
separately each hour makes 4,320 calls in a 30-day month; batching the same
schedule makes 720. POST /v1/prices/batch returns them all in one call, and
one call is what it costs against your quota.

The watchlist below deliberately spans surfaces most integrations never
touch: a crude benchmark, a Permian gas hub, a Santos bunker grade,
carbon, diesel. Your second reason to call is usually one code away.

    OILPRICEAPI_KEY=... python 08_batch_watchlist_dataframe.py

Requires a paid key ($19/mo and up). pandas optional but recommended.
"""

import os

import requests

KEY = os.environ.get("OILPRICEAPI_KEY")
if not KEY:
    raise SystemExit("Set OILPRICEAPI_KEY — free key at https://oilpriceapi.com/auth/signup")

WATCHLIST = [
    "BRENT_CRUDE_USD",      # crude benchmark
    "WTI_USD",
    "NATURAL_GAS_WAHA",     # Permian gas hub (basis market)
    "VLSFO_BRSSZ_USD",      # Santos bunker fuel
    "EU_CARBON_EUR",        # carbon allowances
    "DIESEL_USD",
]

resp = requests.post(
    "https://api.oilpriceapi.com/v1/prices/batch",
    headers={"Authorization": f"Token {KEY}"},
    json={"codes": WATCHLIST},
    timeout=15,
)
resp.raise_for_status()
prices = resp.json()["data"]["prices"]

try:
    import pandas as pd

    df = pd.DataFrame(prices)[["code", "price", "currency", "unit", "as_of"]]
    df["as_of"] = pd.to_datetime(df["as_of"])
    print(df.to_string(index=False))
    df.to_csv("watchlist.csv", index=False)
    print("\nsaved watchlist.csv")
except ImportError:
    for p in prices:
        print(f"{p['code']:<22} {p['price']:>10} {p['unit']}")

# One batch call = one request against your quota, however many codes.
# For push instead of poll, see the alerts & subscriptions endpoints.
