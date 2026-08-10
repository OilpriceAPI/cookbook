"""A production client in 40 lines — errors, 429 backoff, quota headers.

The first error a free-tier integration meets is the 200-request monthly
cap. This recipe shows what the API's errors actually look like and how
to handle them, instead of a stack trace.

Every error response carries a structured envelope:

    {"error": {"code": "UNAUTHORIZED", "message": "...", "status": 401,
               "request_id": "...", "docs": "https://docs.oilpriceapi.com#..."}}

Keep the request_id — support can trace the exact request from it.

    OILPRICEAPI_KEY=... python 10_resilient_client.py
"""

import os
import time

import requests

KEY = os.environ.get("OILPRICEAPI_KEY")
if not KEY:
    raise SystemExit("Set OILPRICEAPI_KEY — free key at https://oilpriceapi.com/auth/signup")

BASE = "https://api.oilpriceapi.com"


def call(path: str, params: dict | None = None, retries: int = 3) -> dict:
    for attempt in range(retries):
        resp = requests.get(
            f"{BASE}{path}",
            headers={"Authorization": f"Token {KEY}"},
            params=params,
            timeout=10,
        )
        if resp.status_code == 429:
            wait = int(resp.headers.get("Retry-After", 2 ** attempt))
            time.sleep(wait)
            continue
        if resp.ok:
            return resp.json()
        err = resp.json().get("error", {})
        raise RuntimeError(
            f"{err.get('code', resp.status_code)}: {err.get('message', 'unknown')} "
            f"(request_id={err.get('request_id', '?')} docs={err.get('docs', '')})"
        )
    raise RuntimeError("rate-limited after retries")


data = call("/v1/prices/latest", {"by_code": "BRENT_CRUDE_USD"})
print(data["data"]["code"], data["data"]["price"])

# Watch your quota as you go — the response carries usage headers; check
# your plan and remaining calls anytime:
#   GET /v1/dashboard  -> usage.current_month.{used,remaining,reset_at}
usage = call("/v1/dashboard")["data"]["usage"]["current_month"]
print(f"quota: {usage['used']} used, {usage['remaining']} remaining, resets {usage['reset_at'][:10]}")
