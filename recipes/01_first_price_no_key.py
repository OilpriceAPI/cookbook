"""Get a live oil price — no API key, no signup.

The demo endpoint serves real, delayed prices for 37 commodities.
Try the API before creating a key.

    python 01_first_price_no_key.py
"""

import requests

resp = requests.get("https://api.oilpriceapi.com/v1/demo/prices/latest", timeout=10)
resp.raise_for_status()

for price in resp.json()["data"]["prices"][:5]:
    print(f"{price['code']:<22} ${price['price']:>9}")

# Free key (50 requests/day): https://oilpriceapi.com/auth/signup
