#!/usr/bin/env python3
"""Set up a price alert that POSTs to your webhook receiver when it fires.

An alert with a webhook_url delivers only to a URL that is also registered at
/v1/webhooks, active, subscribed to `alert.triggered`, and not filtered away
from the alert's commodity. The API refuses the alert otherwise. So the order is:

    1. POST /v1/webhooks   {url, events: ["alert.triggered"], commodity_filters: [code]}
       -> keep the returned `secret` for the receiver (recipe 14)
    2. POST /v1/alerts     {price_alert: {commodity_code, condition_operator,
                            condition_value, webhook_url, cooldown_minutes}}
    3. POST /v1/alerts/{id}/test  -> evaluates the condition against the latest price

    OILPRICEAPI_KEY=... python recipes/15_alert_to_webhook.py \\
        --url https://your-host.example/hooks/oilpriceapi --above 6.50

Operators: greater_than, less_than, equals, greater_than_or_equal,
less_than_or_equal. cooldown_minutes is 0-1440. Webhooks need the Starter plan
or above (plans: https://oilpriceapi.com/pricing). --cleanup deletes both
resources after the test, which is how this recipe was verified.

Real output, run 2026-11-10 (URL was a placeholder https host; threshold set
where it could not fire; both resources deleted by --cleanup):

    webhook e8b6a8d1-ce5f-4f73-b987-fd1245e7bd14 status=active events=['alert.triggered']
      store this secret for the receiver: OILPRICEAPI_WEBHOOK_SECRET=<webhook secret>
    alert 132: DIESEL_RETAIL_USD above 50.0: DIESEL_RETAIL_USD > 50.0 has_webhook=True
    test: price 6.292 -> Alert condition not met (would_trigger=False)
    cleanup: alert and webhook deleted

Sign up: https://oilpriceapi.com/auth/signup?utm_source=github_examples&utm_medium=integration&utm_campaign=acq_q4
"""

from __future__ import annotations

import argparse
import os

import requests

BASE = "https://api.oilpriceapi.com"


def api(session: requests.Session, method: str, path: str, **kwargs) -> dict | None:
    resp = session.request(method, f"{BASE}{path}", timeout=30, **kwargs)
    if not resp.ok:
        raise RuntimeError(f"{method} {path} -> {resp.status_code}: {resp.text[:500]}")
    return resp.json() if resp.content else None


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a webhook-delivered price alert.")
    parser.add_argument("--url", required=True, help="your HTTPS receiver URL")
    parser.add_argument("--code", default="DIESEL_RETAIL_USD", help="commodity code")
    parser.add_argument("--above", type=float, required=True, help="fire when price > this")
    parser.add_argument("--cooldown", type=int, default=60, help="minutes between fires")
    parser.add_argument("--cleanup", action="store_true", help="delete both after the test")
    args = parser.parse_args()

    key = os.environ.get("OILPRICEAPI_KEY")
    if not key or not args.url.startswith("https://"):
        parser.error("set OILPRICEAPI_KEY and pass an https:// --url")

    session = requests.Session()
    session.headers.update(
        {"Authorization": f"Token {key}", "User-Agent": "oilpriceapi-cookbook/1"}
    )

    webhook = api(
        session,
        "POST",
        "/v1/webhooks",
        json={
            "url": args.url,
            "events": ["alert.triggered"],
            "commodity_filters": [args.code],
            "description": f"Alerts for {args.code}",
        },
    )
    alert_id = None
    try:
        print(f"webhook {webhook['id']} status={webhook['status']} events={webhook['events']}")
        # The secret is in this response and in GET /v1/webhooks/{id}; keep it out of logs.
        print("  store this secret for the receiver: OILPRICEAPI_WEBHOOK_SECRET=<webhook secret>")

        alert = api(
            session,
            "POST",
            "/v1/alerts",
            json={
                "price_alert": {
                    "name": f"{args.code} above {args.above}",
                    "commodity_code": args.code,
                    "condition_operator": "greater_than",
                    "condition_value": args.above,
                    "webhook_url": args.url,
                    "cooldown_minutes": args.cooldown,
                }
            },
        )
        alert_id = alert["id"]
        print(f"alert {alert_id}: {alert['summary']} has_webhook={alert['has_webhook']}")

        test = api(session, "POST", f"/v1/alerts/{alert_id}/test")
        print(
            f"test: price {test['current_price']['value']} -> {test['result']} "
            f"(would_trigger={test['would_trigger']})"
        )
        return 0
    finally:
        if args.cleanup:
            if alert_id:
                api(session, "DELETE", f"/v1/alerts/{alert_id}")
            api(session, "DELETE", f"/v1/webhooks/{webhook['id']}")
            print("cleanup: alert and webhook deleted")


if __name__ == "__main__":
    raise SystemExit(main())
