import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
RECIPE_PATH = ROOT / "recipes" / "10_resilient_client.py"


class FakeResponse:
    def __init__(self, status_code, *, payload=None, headers=None):
        self.status_code = status_code
        self.ok = 200 <= status_code < 300
        self._payload = payload or {}
        self.headers = headers or {}

    def json(self):
        return self._payload


def quota_headers(**overrides):
    values = {
        "X-RateLimit-Limit": "50",
        "X-RateLimit-Remaining": "48",
        "X-RateLimit-Used": "2",
        "X-RateLimit-Window": "daily",
        "X-RateLimit-State": "available",
        "X-RateLimit-Reset": "1786507200",
    }
    values.update(overrides)
    return values


class ResilientClientTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("resilient_client", RECIPE_PATH)
        cls.module = importlib.util.module_from_spec(spec)
        requests_module = types.ModuleType("requests")
        requests_module.Response = FakeResponse
        requests_module.get = Mock()
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.dict(sys.modules, {"requests": requests_module}),
        ):
            spec.loader.exec_module(cls.module)
        requests_module.get.assert_not_called()

    def test_success_returns_payload_and_canonical_quota(self):
        response = FakeResponse(
            200,
            payload={"data": {"code": "BRENT_CRUDE_USD", "price": 80.0}},
            headers=quota_headers(),
        )

        with patch.object(self.module.requests, "get", return_value=response):
            payload, quota = self.module.call("key", "/v1/prices/latest")

        self.assertEqual("BRENT_CRUDE_USD", payload["data"]["code"])
        self.assertEqual(
            {
                "limit": "50",
                "remaining": "48",
                "used": "2",
                "window": "daily",
                "state": "available",
                "reset": "1786507200",
            },
            quota,
        )

    def test_missing_quota_header_fails_closed(self):
        headers = quota_headers()
        del headers["X-RateLimit-Reset"]
        response = FakeResponse(200, payload={"data": {}}, headers=headers)

        with patch.object(self.module.requests, "get", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "omitted quota headers.*X-RateLimit-Reset"):
                self.module.call("key", "/v1/prices/latest")

    def test_daily_exhaustion_does_not_retry_or_sleep(self):
        response = FakeResponse(
            429,
            headers=quota_headers(
                **{
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Used": "50",
                    "X-RateLimit-State": "exhausted",
                    "Retry-After": "3600",
                }
            ),
        )

        with (
            patch.object(self.module.requests, "get", return_value=response) as request,
            patch.object(self.module.time, "sleep") as sleep,
        ):
            with self.assertRaisesRegex(RuntimeError, "quota exhausted.*daily window"):
                self.module.call("key", "/v1/prices/latest")

        request.assert_called_once()
        sleep.assert_not_called()

    def test_transient_hourly_limit_honors_retry_after_then_succeeds(self):
        limited = FakeResponse(
            429,
            headers=quota_headers(
                **{
                    "X-RateLimit-Window": "hourly_circuit_breaker",
                    "X-RateLimit-State": "exhausted",
                    "Retry-After": "2",
                }
            ),
        )
        success = FakeResponse(200, payload={"data": {}}, headers=quota_headers())

        with (
            patch.object(self.module.requests, "get", side_effect=[limited, success]),
            patch.object(self.module.time, "sleep") as sleep,
        ):
            _, quota = self.module.call("key", "/v1/prices/latest")

        sleep.assert_called_once_with(2)
        self.assertEqual("daily", quota["window"])


if __name__ == "__main__":
    unittest.main()
