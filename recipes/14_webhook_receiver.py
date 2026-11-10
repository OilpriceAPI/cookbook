#!/usr/bin/env python3
"""A webhook receiver that verifies OilPriceAPI signatures. Standard library only.

Every delivery is a POST with a JSON body and these headers:

    X-OilPriceAPI-Signature            hex HMAC-SHA256 of  <raw body> + "." + <timestamp>
    X-OilPriceAPI-Signature-Timestamp  Unix seconds, set when the attempt is sent
    X-OilPriceAPI-Event                e.g. alert.triggered, price.updated, webhook.test
    X-OilPriceAPI-Event-ID             the payload's "id"; the same on every retry

The HMAC key is the endpoint's `secret`, returned by POST /v1/webhooks (and by
GET /v1/webhooks/{id}).
Sign the raw bytes you received. Re-serialising the parsed JSON changes the
bytes (key order, spacing, escaped characters) and the signature stops matching.

Any 2xx counts as delivered. A non-2xx or a timeout is retried, and each retry
is signed again with a fresh timestamp, so a short replay window is safe.

    OILPRICEAPI_WEBHOOK_SECRET=... python recipes/14_webhook_receiver.py
    # then expose port 8765 over HTTPS (a tunnel or your own ingress) and
    # register that URL with POST /v1/webhooks (recipe 15 does this)

Verified 2026-11-10 by tests/test_webhook_receiver.py, which POSTs a delivery
signed by Ruby's OpenSSL::HMAC.hexdigest('SHA256', secret, "#{body}.#{timestamp}")
(the call the API's WebhookDeliveryService makes) to this handler. Real output:

    ALERT Diesel above $6 & rising: DIESEL_RETAIL_USD 6.292 (greater_than 6.0)
    rejected: signature mismatch            <- one number in the body changed
    rejected: signature mismatch            <- wrong signature
    duplicate 5f0e3c1a-...; already handled <- a retry, acknowledged with 204

Registering a webhook needs the Starter plan or above (plans: https://oilpriceapi.com/pricing).
Sign up: https://oilpriceapi.com/auth/signup?utm_source=github_examples&utm_medium=integration&utm_campaign=acq_q4
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = int(os.environ.get("PORT", "8765"))
TOLERANCE_SECONDS = 300  # receiver policy: how old a signed attempt may be
MAX_BODY_BYTES = 1024 * 1024  # the API refuses to send payloads over 1 MB


class Rejected(Exception):
    """The delivery is not provably from OilPriceAPI; answer 400 and drop it."""


def verify(
    body: bytes,
    timestamp: str,
    signature: str,
    secret: str,
    now: float | None = None,
    tolerance: int = TOLERANCE_SECONDS,
) -> dict:
    """Return the parsed payload, or raise Rejected."""
    if not timestamp.isdigit():
        raise Rejected("missing or malformed timestamp")
    if abs((now if now is not None else time.time()) - int(timestamp)) > tolerance:
        raise Rejected(f"timestamp outside {tolerance}s")
    expected = hmac.new(
        secret.encode(), body + b"." + timestamp.encode("ascii"), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, signature.strip().lower()):
        raise Rejected("signature mismatch")
    return json.loads(body)


class SeenEvents:
    """Retries reuse the event id. Store it durably in production; memory here."""

    def __init__(self) -> None:
        self._ids: set[str] = set()

    def first_time(self, event_id: str) -> bool:
        if event_id in self._ids:
            return False
        self._ids.add(event_id)
        return True


def handle(payload: dict) -> None:
    event = payload.get("event")
    data = payload.get("data", {})
    if event == "alert.triggered":
        print(
            f"ALERT {data.get('alert_name')}: {data.get('commodity_code')} "
            f"{data.get('price_value')} ({data.get('threshold_operator')} "
            f"{data.get('threshold_value')})"
        )
    else:
        print(f"{event}: {json.dumps(data)[:200]}")


def make_handler(secret: str, seen: SeenEvents):
    class Receiver(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802 - BaseHTTPRequestHandler API
            length = int(self.headers.get("Content-Length", "0"))
            if length > MAX_BODY_BYTES:
                return self._reply(413)
            body = self.rfile.read(length)
            try:
                payload = verify(
                    body,
                    self.headers.get("X-OilPriceAPI-Signature-Timestamp", ""),
                    self.headers.get("X-OilPriceAPI-Signature", ""),
                    secret,
                )
            except (Rejected, ValueError) as error:
                print(f"rejected: {error}")
                return self._reply(400)
            event_id = self.headers.get("X-OilPriceAPI-Event-ID") or payload.get("id", "")
            if seen.first_time(event_id):
                handle(payload)
            else:
                print(f"duplicate {event_id}; already handled")
            self._reply(204)  # answer fast; do slow work after acknowledging

        def _reply(self, status: int) -> None:
            self.send_response(status)
            self.end_headers()

        def log_message(self, *_args):
            pass

    return Receiver


def main() -> None:
    secret = os.environ.get("OILPRICEAPI_WEBHOOK_SECRET", "")
    if not secret:
        raise SystemExit("set OILPRICEAPI_WEBHOOK_SECRET to the secret POST /v1/webhooks returned")
    server = HTTPServer(("0.0.0.0", PORT), make_handler(secret, SeenEvents()))
    print(f"listening on :{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
