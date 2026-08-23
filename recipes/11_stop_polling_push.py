#!/usr/bin/env python3
"""Create and verify an alert, signed webhook, and scheduled price watch.

This recipe writes temporary production resources and always deletes them. Start
an HTTPS tunnel to localhost:8765, set WEBHOOK_PUBLIC_URL to its public URL, then:

    OILPRICEAPI_KEY=... WEBHOOK_PUBLIC_URL=https://... \
      python recipes/11_stop_polling_push.py --execute

Price alerts and webhooks require an entitled paid plan. Watches are available
on every plan; the minimum interval varies by entitlement.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import queue
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen


API = "https://api.oilpriceapi.com"
PORT = 8765


def verify_signature(payload: bytes, timestamp: str, signature: str, secret: str) -> bool:
    message = payload + b"." + timestamp.encode("ascii")
    expected = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def request_json(key: str, method: str, path: str, body: dict[str, Any] | None = None):
    payload = json.dumps(body).encode() if body is not None else None
    request = Request(
        f"{API}{path}",
        data=payload,
        method=method,
        headers={
            "Authorization": f"Token {key}",
            "Content-Type": "application/json",
            "User-Agent": "oilpriceapi-cookbook/1",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read()
            return json.loads(raw) if raw else None
    except HTTPError as error:
        detail = error.read().decode("utf-8", "replace")
        raise RuntimeError(f"{method} {path} failed ({error.code}): {detail}") from error


class Receiver(BaseHTTPRequestHandler):
    deliveries: queue.Queue[tuple[bytes, str, str]] = queue.Queue()

    def do_POST(self):  # noqa: N802 - BaseHTTPRequestHandler API
        payload = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        self.deliveries.put(
            (
                payload,
                self.headers.get("X-OilPriceAPI-Signature-Timestamp", ""),
                self.headers.get("X-OilPriceAPI-Signature", ""),
            )
        )
        self.send_response(204)
        self.end_headers()

    def log_message(self, *_args):
        pass


def delete_quietly(key: str, path: str) -> None:
    try:
        request_json(key, "DELETE", path)
    except Exception as error:  # cleanup must continue for the other resources
        print(f"cleanup warning for {path}: {error}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="create temporary resources")
    args = parser.parse_args()
    if not args.execute:
        parser.error("this recipe writes temporary resources; pass --execute after reading it")

    key = os.environ.get("OILPRICEAPI_KEY", "")
    webhook_url = os.environ.get("WEBHOOK_PUBLIC_URL", "")
    if not key or not webhook_url.startswith("https://"):
        parser.error("set OILPRICEAPI_KEY and an HTTPS WEBHOOK_PUBLIC_URL tunnel")

    server = HTTPServer(("127.0.0.1", PORT), Receiver)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    alert_id = webhook_id = watch_id = None
    try:
        alert = request_json(
            key,
            "POST",
            "/v1/alerts",
            {
                "price_alert": {
                    "name": "Cookbook: WTI above $9,999",
                    "commodity_code": "WTI_USD",
                    "condition_operator": "greater_than",
                    "condition_value": 9999,
                    "cooldown_minutes": 60,
                }
            },
        )
        alert_id = alert["id"]
        result = request_json(key, "POST", f"/v1/alerts/{alert_id}/test")
        print(f"email alert verified: would_trigger={result['would_trigger']}")

        webhook = request_json(
            key,
            "POST",
            "/v1/webhooks",
            {
                "url": webhook_url,
                "events": ["price.updated"],
                "description": "Cookbook signed-delivery verification",
            },
        )
        webhook_id, secret = webhook["id"], webhook["secret"]
        request_json(key, "POST", f"/v1/webhooks/{webhook_id}/test")
        verified = False
        for _ in range(3):
            payload, timestamp, signature = Receiver.deliveries.get(timeout=30)
            if verify_signature(payload, timestamp, signature, secret):
                verified = True
                break
        if not verified:
            raise RuntimeError("test webhook arrived but its signature did not verify")
        print("webhook verified: signed test delivery accepted")

        watch = request_json(
            key,
            "POST",
            "/v1/subscriptions",
            {
                "name": "Cookbook: crude desk hourly",
                "codes": ["BRENT_CRUDE_USD", "WTI_USD"],
                "interval_seconds": 3600,
            },
        )["data"]["subscription"]
        watch_id = watch["id"]
        print(f"watch active: next_run_at={watch['next_run_at']}")
        print("quota math: polling every 5 minutes = 8,640 calls/30 days; push setup = 3 writes")
        return 0
    finally:
        if watch_id:
            delete_quietly(key, f"/v1/subscriptions/{watch_id}")
        if webhook_id:
            delete_quietly(key, f"/v1/webhooks/{webhook_id}")
        if alert_id:
            delete_quietly(key, f"/v1/alerts/{alert_id}")
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    raise SystemExit(main())
