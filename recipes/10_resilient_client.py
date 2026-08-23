"""A compact production client — errors, bounded 429 backoff, quota headers.

The Free allowance is 50 requests/day. This recipe reads the effective limit,
window, state, and reset from the same response the API just served, so it also
works for paid, trial, credit, and courtesy entitlements.

Every error response carries a structured envelope:

    {"error": {"code": "UNAUTHORIZED", "message": "...", "status": 401,
               "request_id": "...", "docs": "https://docs.oilpriceapi.com#..."}}

Keep the request_id — support can trace the exact request from it.

    OILPRICEAPI_KEY=... python 10_resilient_client.py
"""

import os
import time
from datetime import datetime, timezone

import requests

BASE = "https://api.oilpriceapi.com"
QUOTA_HEADERS = {
    "limit": "X-RateLimit-Limit",
    "remaining": "X-RateLimit-Remaining",
    "used": "X-RateLimit-Used",
    "window": "X-RateLimit-Window",
    "state": "X-RateLimit-State",
    "reset": "X-RateLimit-Reset",
}


def quota_from(response: requests.Response) -> dict[str, str]:
    quota = {name: response.headers.get(header) for name, header in QUOTA_HEADERS.items()}
    missing = [QUOTA_HEADERS[name] for name, value in quota.items() if value is None]
    if missing:
        raise RuntimeError(f"response omitted quota headers: {', '.join(missing)}")
    return quota


def call(
    key: str, path: str, params: dict | None = None, retries: int = 3
) -> tuple[dict, dict[str, str]]:
    for attempt in range(retries):
        resp = requests.get(
            f"{BASE}{path}",
            headers={"Authorization": f"Token {key}"},
            params=params,
            timeout=10,
        )
        if resp.status_code == 429:
            quota = quota_from(resp)
            if quota["state"] == "exhausted" and quota["window"] in {"daily", "day"}:
                raise RuntimeError(
                    f"quota exhausted: {quota['used']}/{quota['limit']} in the "
                    f"{quota['window']} window; reset={quota['reset']}"
                )
            wait = min(int(resp.headers.get("Retry-After", 2**attempt)), 30)
            time.sleep(wait)
            continue
        if resp.ok:
            return resp.json(), quota_from(resp)
        err = resp.json().get("error", {})
        raise RuntimeError(
            f"{err.get('code', resp.status_code)}: {err.get('message', 'unknown')} "
            f"(request_id={err.get('request_id', '?')} docs={err.get('docs', '')})"
        )
    raise RuntimeError("rate-limited after retries")


def main() -> None:
    key = os.environ.get("OILPRICEAPI_KEY")
    if not key:
        raise SystemExit(
            "Set OILPRICEAPI_KEY — free key at https://oilpriceapi.com/auth/signup"
        )

    data, quota = call(key, "/v1/prices/latest", {"by_code": "BRENT_CRUDE_USD"})
    print(data["data"]["code"], data["data"]["price"])

    reset_at = datetime.fromtimestamp(int(quota["reset"]), tz=timezone.utc).isoformat()
    print(
        f"quota: {quota['used']}/{quota['limit']} used in the {quota['window']} window, "
        f"{quota['remaining']} remaining, state={quota['state']}, resets {reset_at}"
    )


if __name__ == "__main__":
    main()
