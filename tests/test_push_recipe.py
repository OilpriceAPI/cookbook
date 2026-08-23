import hashlib
import hmac
import unittest

from recipes import _push_recipe


class PushRecipeTest(unittest.TestCase):
    def test_signature_accepts_exact_payload_and_timestamp(self):
        payload = b'{"type":"price.updated"}'
        timestamp = "1787525183"
        secret = "whsec_fixture"
        signature = hmac.new(
            secret.encode(), payload + b"." + timestamp.encode(), hashlib.sha256
        ).hexdigest()

        self.assertTrue(_push_recipe.verify_signature(payload, timestamp, signature, secret))
        self.assertFalse(
            _push_recipe.verify_signature(payload + b" ", timestamp, signature, secret)
        )


if __name__ == "__main__":
    unittest.main()
