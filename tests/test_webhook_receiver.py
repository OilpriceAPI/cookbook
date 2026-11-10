"""The receiver must accept a delivery signed the way the API signs it.

tests/fixtures/webhook_delivery.json was produced by Ruby's
OpenSSL::HMAC.hexdigest('SHA256', secret, "#{body}.#{timestamp}") -- the exact
call in oilpriceapi-api app/services/webhook_delivery_service.rb -- so this test
does not merely agree with itself.
"""

import json
import threading
import unittest
from http.server import HTTPServer
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
_spec = spec_from_file_location("webhook_receiver", ROOT / "recipes" / "14_webhook_receiver.py")
assert _spec and _spec.loader
receiver = module_from_spec(_spec)
_spec.loader.exec_module(receiver)

FIXTURE = json.loads((ROOT / "tests" / "fixtures" / "webhook_delivery.json").read_text())
BODY = FIXTURE["body"].encode()
TS = FIXTURE["timestamp"]
SIG = FIXTURE["signature"]
SECRET = FIXTURE["secret"]
NOW = int(TS) + 5


class VerifyTest(unittest.TestCase):
    def test_accepts_api_signed_delivery(self):
        payload = receiver.verify(BODY, TS, SIG, SECRET, now=NOW)
        self.assertEqual(payload["event"], "alert.triggered")
        self.assertEqual(payload["data"]["commodity_code"], "DIESEL_RETAIL_USD")

    def test_rejects_tampered_body(self):
        tampered = BODY.replace(b"6.292", b"6.293")
        with self.assertRaisesRegex(receiver.Rejected, "signature mismatch"):
            receiver.verify(tampered, TS, SIG, SECRET, now=NOW)

    def test_rejects_reserialised_body(self):
        # json.dumps adds spaces: the same data, different bytes, no match.
        reserialised = json.dumps(json.loads(BODY)).encode()
        with self.assertRaises(receiver.Rejected):
            receiver.verify(reserialised, TS, SIG, SECRET, now=NOW)

    def test_rejects_wrong_secret_and_moved_timestamp(self):
        with self.assertRaises(receiver.Rejected):
            receiver.verify(BODY, TS, SIG, "0" * 64, now=NOW)
        with self.assertRaises(receiver.Rejected):
            receiver.verify(BODY, str(int(TS) + 1), SIG, SECRET, now=NOW)

    def test_rejects_stale_replay_and_missing_timestamp(self):
        with self.assertRaisesRegex(receiver.Rejected, "outside"):
            receiver.verify(BODY, TS, SIG, SECRET, now=int(TS) + 600)
        with self.assertRaisesRegex(receiver.Rejected, "timestamp"):
            receiver.verify(BODY, "", SIG, SECRET, now=NOW)


class HttpTest(unittest.TestCase):
    """Drive the real handler over HTTP, as the API's POST would."""

    def setUp(self):
        self.seen = receiver.SeenEvents()
        self.server = HTTPServer(("127.0.0.1", 0), receiver.make_handler(SECRET, self.seen))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/hook"
        self._time = receiver.time.time
        receiver.time.time = lambda: NOW

    def tearDown(self):
        receiver.time.time = self._time
        self.server.shutdown()
        self.server.server_close()

    def post(self, body: bytes, signature: str = SIG) -> int:
        request = Request(
            self.url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-OilPriceAPI-Signature": signature,
                "X-OilPriceAPI-Signature-Timestamp": TS,
                "X-OilPriceAPI-Event": "alert.triggered",
                "X-OilPriceAPI-Event-ID": "5f0e3c1a-7d2b-4c0e-9a51-2b7f4d8e6c13",
            },
        )
        try:
            with urlopen(request, timeout=5) as response:
                return response.status
        except HTTPError as error:
            return error.code

    def test_accepts_signed_rejects_tampered_and_dedupes_retry(self):
        self.assertEqual(self.post(BODY), 204)
        self.assertEqual(self.post(BODY.replace(b"6.292", b"9.999")), 400)
        self.assertEqual(self.post(BODY, signature="0" * 64), 400)
        self.assertEqual(self.post(BODY), 204)  # a retry is acknowledged
        self.assertFalse(self.seen.first_time("5f0e3c1a-7d2b-4c0e-9a51-2b7f4d8e6c13"))


if __name__ == "__main__":
    unittest.main()
