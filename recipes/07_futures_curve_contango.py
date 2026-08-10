"""Read a futures curve and name the market structure.

The curve endpoint returns every contract month plus a structure call
(contango or backwardation). One request answers "is the market paying
you to store oil?"

    OILPRICEAPI_KEY=... python 07_futures_curve_contango.py

Requires Professional ($99/mo) or higher.
"""

import os

import requests

KEY = os.environ.get("OILPRICEAPI_KEY")
if not KEY:
    raise SystemExit("Set OILPRICEAPI_KEY — free key at https://oilpriceapi.com/auth/signup")

resp = requests.get(
    "https://api.oilpriceapi.com/v1/futures/ice-brent/curve",
    headers={"Authorization": f"Token {KEY}"},
    timeout=10,
)
resp.raise_for_status()
data = resp.json()

contracts = data["contracts"]
front, back = contracts[0], contracts[-1]
print(f"Brent curve: {len(contracts)} contracts ({data['curve_type']})")
print(f"front {front['contract_month']}  ${front['settlement_price']}")
print(f"back  {back['contract_month']}  ${back['settlement_price']}")

# Slugs: ice-brent, ice-wti, ice-gasoil, natural-gas, ttf-gas, lng-jkm,
# eua-carbon, uk-carbon. Front-month only: GET /v1/futures/{slug}
