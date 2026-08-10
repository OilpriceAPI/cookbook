"""Marine (bunker) fuel prices by port.

VLSFO, MGO and HFO 380 assessments for major bunkering ports — Singapore,
Rotterdam, Fujairah, Houston, plus Santos, Istanbul and Piraeus. Codes
follow one pattern: <FUEL>_<UNLOCODE>_USD.

    OILPRICEAPI_KEY=... python 04_bunker_prices_by_port.py

Requires a paid key with marine coverage (Professional, $99/mo and up,
for the port endpoints; the flat codes below work on any paid key).
"""

import os

import requests

KEY = os.environ.get("OILPRICEAPI_KEY")
if not KEY:
    raise SystemExit("Set OILPRICEAPI_KEY — free key at https://oilpriceapi.com/auth/signup")
HEADERS = {"Authorization": f"Token {KEY}"}

CODES = [
    "VLSFO_SGSIN_USD",   # Singapore
    "VLSFO_NLRTM_USD",   # Rotterdam
    "VLSFO_BRSSZ_USD",   # Santos
    "MGO_05S_BRSSZ_USD", # Santos MGO
]

for code in CODES:
    resp = requests.get(
        "https://api.oilpriceapi.com/v1/prices/latest",
        headers=HEADERS, params={"by_code": code}, timeout=10,
    )
    if resp.status_code in (401, 402, 403):
        # Surface the API's own explanation instead of faking an empty result
        raise SystemExit(f"{resp.status_code}: {resp.json().get('error', {}).get('message', resp.text[:200])}")
    data = resp.json().get("data", {}) if resp.ok else {}
    shown = f"${data['price']}" if data.get("price") is not None else "no assessment"
    print(f"{code:<20} {shown}")

# Port detail with fuel grades (ISO 8217) and port list:
#   GET /v1/prices/marine-fuels/latest?port=SINGAPORE
#   GET /v1/prices/marine-fuels/ports
