import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.check_public_claims import ClaimCheckError, check_repository, load_product_facts


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
STALE_FREE_ALLOWANCE_VARIANTS = (
    "Free tier includes 200 requests per month.",
    "Free plan includes 200 API calls/month.",
    "Free account includes 200-API-calls-per-month.",
    "Free key includes 200 requests-per-month.",
    "Free tier includes 200 monthly requests.",
    "Free tier includes 200 requests per day.",
    "Free plan includes 200 API calls/day.",
    "Free account includes 200-API-calls-per-day.",
    "Free key includes 200 requests-per-day.",
    "Free tier includes 200 daily requests.",
)


class FakeResponse:
    def __init__(self, payload, final_url):
        self.payload = payload
        self.final_url = final_url

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, *_args):
        return self.payload

    def geturl(self):
        return self.final_url


class PublicClaimCheckTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name) / "cookbook"
        ignored = shutil.ignore_patterns(".git", ".venv", "__pycache__")
        shutil.copytree(ROOT, self.root, ignore=ignored)
        self.product_facts = load_product_facts(FIXTURES / "product-facts-50.json")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_current_repository_matches_canonical_fixture(self):
        check_repository(self.root, self.product_facts)

    def test_changed_canonical_allowance_fails(self):
        changed_facts = load_product_facts(FIXTURES / "product-facts-51.json")

        with self.assertRaisesRegex(
            ClaimCheckError,
            "canonical free allowance is 51 requests/day.*local claim is 50 requests/day",
        ):
            check_repository(self.root, changed_facts)

    def test_new_stale_allowance_claim_fails(self):
        recipe = self.root / "recipes" / "09_agent_tool.py"
        recipe.write_text(
            recipe.read_text(encoding="utf-8") + "\n# Free key: 200 requests/day.\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(
            ClaimCheckError,
            "canonical free allowance is 50 requests/day.*local claim is 200 requests/day",
        ):
            check_repository(self.root, self.product_facts)

    def test_nested_recipe_stale_allowance_claim_fails(self):
        recipe = self.root / "recipes" / "integrations" / "client.py"
        recipe.parent.mkdir()
        recipe.write_text("# Free key: 200 requests/day.\n", encoding="utf-8")

        with self.assertRaisesRegex(
            ClaimCheckError,
            "recipes/integrations/client.py: canonical free allowance is 50 requests/day",
        ):
            check_repository(self.root, self.product_facts)

    def test_wrapped_stale_allowance_claim_fails(self):
        recipe = self.root / "recipes" / "09_agent_tool.py"
        recipe.write_text(
            recipe.read_text(encoding="utf-8")
            + "\n# The Free tier includes\n# 200 requests per day.\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(
            ClaimCheckError,
            "canonical free allowance is 50 requests/day.*local claim is 200 requests/day",
        ):
            check_repository(self.root, self.product_facts)

    def test_alternate_stale_free_allowance_wording_fails(self):
        recipe = self.root / "recipes" / "09_agent_tool.py"
        original = recipe.read_text(encoding="utf-8")

        for stale_claim in STALE_FREE_ALLOWANCE_VARIANTS:
            with self.subTest(stale_claim=stale_claim):
                recipe.write_text(f"{original}\n# {stale_claim}\n", encoding="utf-8")
                with self.assertRaisesRegex(
                    ClaimCheckError,
                    "canonical free allowance is 50 requests/day.*local claim is 200",
                ):
                    check_repository(self.root, self.product_facts)

    def test_isolated_stale_free_table_value_fails(self):
        readme = self.root / "README.md"
        readme.write_text(
            readme.read_text(encoding="utf-8")
            + "\n| Plan | API calls / day | Price |\n"
            + "| --- | ---: | ---: |\n"
            + "| Free | 200 | $0 |\n"
            + "| Developer | 10,000 | $19 |\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(
            ClaimCheckError,
            "canonical free allowance is 50 requests/day.*local claim is 200 requests/day",
        ):
            check_repository(self.root, self.product_facts)

    def test_current_free_and_paid_allowances_pass(self):
        readme = self.root / "README.md"
        readme.write_text(
            readme.read_text(encoding="utf-8")
            + "\nFree remains at 50 requests/day, while Developer includes "
            + "10,000 requests per month at $19. Professional includes "
            + "100,000 API calls/month at $99.\n"
            + "\n| Tier | Requests per day | Price |\n"
            + "| --- | ---: | ---: |\n"
            + "| Free | **50** | $0 |\n"
            + "| Developer | 10,000 | $19 |\n"
            + "| Professional | 100,000 | $99 |\n",
            encoding="utf-8",
        )

        check_repository(self.root, self.product_facts)

    def test_monthly_free_claim_fails_even_when_count_matches(self):
        readme = self.root / "README.md"
        readme.write_text(
            readme.read_text(encoding="utf-8").replace(
                "50 requests/day", "50 requests/month"
            ),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(
            ClaimCheckError,
            "canonical free allowance is 50 requests/day.*local claim is 50 requests/month",
        ):
            check_repository(self.root, self.product_facts)

    def test_monthly_paid_claim_is_not_treated_as_free(self):
        readme = self.root / "README.md"
        readme.write_text(
            readme.read_text(encoding="utf-8")
            + "\nFree remains at 50 requests/day, while Developer includes "
            + "10,000 requests per month and Professional includes 100,000/month.\n",
            encoding="utf-8",
        )

        check_repository(self.root, self.product_facts)

    def test_product_facts_v1_is_rejected_as_legacy(self):
        legacy = {
            "schemaVersion": "1.0.0",
            "contractVersion": "2026-07-18",
            "reviewedAt": "2026-07-18",
            "canonicalUrl": "https://api.oilpriceapi.com/product-facts.json",
            "offer": {"freeRequestsPerMonth": 50},
        }

        with self.assertRaisesRegex(ClaimCheckError, "schemaVersion must be exactly 2.0.0"):
            check_repository(self.root, legacy)

    def test_unknown_schema_version_is_rejected(self):
        for version in ("2foo", "2.0", "3.0.0"):
            with self.subTest(version=version):
                facts = copy.deepcopy(self.product_facts)
                facts["schemaVersion"] = version
                with self.assertRaisesRegex(
                    ClaimCheckError, "schemaVersion must be exactly 2.0.0"
                ):
                    check_repository(self.root, facts)

    def test_unknown_root_and_nested_fields_are_rejected(self):
        for path in (("unexpected",), ("offer", "unexpected")):
            with self.subTest(path=path):
                facts = copy.deepcopy(self.product_facts)
                target = facts
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = "unreviewed"
                with self.assertRaisesRegex(ClaimCheckError, "unexpected fields"):
                    check_repository(self.root, facts)

    def test_missing_required_field_is_rejected(self):
        facts = copy.deepcopy(self.product_facts)
        del facts["developer"]["firstRequestPath"]

        with self.assertRaisesRegex(ClaimCheckError, "missing fields"):
            check_repository(self.root, facts)

    def test_invalid_typed_allowance_is_rejected(self):
        for value in (True, 0, "50"):
            with self.subTest(value=value):
                facts = copy.deepcopy(self.product_facts)
                facts["offer"]["freeRequestLimit"] = value
                with self.assertRaisesRegex(
                    ClaimCheckError, "offer.freeRequestLimit must be a positive integer"
                ):
                    check_repository(self.root, facts)

    def test_invalid_window_is_rejected(self):
        for window in ("daily", "year", 1):
            with self.subTest(window=window):
                facts = copy.deepcopy(self.product_facts)
                facts["offer"]["freeRequestWindow"] = window
                with self.assertRaisesRegex(
                    ClaimCheckError, "offer.freeRequestWindow must be day or month"
                ):
                    check_repository(self.root, facts)

    def test_schema_and_canonical_urls_are_exact(self):
        cases = (
            ("schemaUrl", "https://example.com/product-facts-v2.schema.json"),
            ("canonicalUrl", "https://example.com/product-facts.json"),
        )
        for key, value in cases:
            with self.subTest(key=key):
                facts = copy.deepcopy(self.product_facts)
                facts[key] = value
                with self.assertRaisesRegex(ClaimCheckError, f"{key} must be exactly"):
                    check_repository(self.root, facts)

    def test_provenance_must_be_equal_valid_non_future_dates(self):
        cases = (
            ("2026-08-10", "2026-08-11"),
            ("2026-02-30", "2026-02-30"),
            ("2999-01-01", "2999-01-01"),
        )
        for contract_version, reviewed_at in cases:
            with self.subTest(contract_version=contract_version):
                facts = copy.deepcopy(self.product_facts)
                facts["contractVersion"] = contract_version
                facts["reviewedAt"] = reviewed_at
                with self.assertRaisesRegex(ClaimCheckError, "provenance"):
                    check_repository(self.root, facts)

    def test_remote_fetch_rejects_noncanonical_source(self):
        with patch("scripts.check_public_claims.urlopen") as opener:
            with self.assertRaisesRegex(ClaimCheckError, "source URL must be exactly"):
                load_product_facts("https://example.com/product-facts.json")
        opener.assert_not_called()

    def test_remote_fetch_rejects_cross_origin_redirect(self):
        payload = json.dumps(self.product_facts).encode("utf-8")
        response = FakeResponse(payload, "https://example.com/product-facts.json")
        with patch("scripts.check_public_claims.urlopen", return_value=response):
            with self.assertRaisesRegex(ClaimCheckError, "redirected away"):
                load_product_facts()

    def test_remote_fetch_accepts_exact_canonical_response(self):
        payload = json.dumps(self.product_facts).encode("utf-8")
        response = FakeResponse(payload, "https://api.oilpriceapi.com/product-facts.json")
        with patch("scripts.check_public_claims.urlopen", return_value=response):
            self.assertEqual(self.product_facts, load_product_facts())

    def test_duplicate_json_keys_are_rejected(self):
        fixture = self.root / "duplicate-product-facts.json"
        payload = json.dumps(self.product_facts)
        fixture.write_text(
            payload.replace(
                '"schemaVersion": "2.0.0"',
                '"schemaVersion": "1.0.0", "schemaVersion": "2.0.0"',
                1,
            ),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ClaimCheckError, "duplicate JSON field"):
            load_product_facts(fixture)

    def test_quota_recipe_uses_windowed_response_headers(self):
        recipe = (self.root / "recipes" / "10_resilient_client.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("/v1/dashboard", recipe)
        self.assertNotIn("current_month", recipe)
        for header in (
            "X-RateLimit-Limit",
            "X-RateLimit-Remaining",
            "X-RateLimit-Used",
            "X-RateLimit-Window",
            "X-RateLimit-State",
            "X-RateLimit-Reset",
        ):
            self.assertIn(header, recipe)

    def test_smoke_workflow_uses_immutable_actions_and_read_only_checkout(self):
        workflow = (self.root / ".github" / "workflows" / "smoke.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertRegex(workflow, r"actions/checkout@[0-9a-f]{40}")
        self.assertRegex(workflow, r"actions/setup-python@[0-9a-f]{40}")
        self.assertIn("persist-credentials: false", workflow)
        self.assertNotRegex(workflow, r"uses:\s+[^\s]+@v\d+")

    def test_broad_as_of_wording_fails(self):
        readme = self.root / "README.md"
        readme.write_text(
            readme.read_text(encoding="utf-8")
            + "\n`as_of` works on any history endpoint and reconstructs any date.\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ClaimCheckError, "forbidden broad as_of claim"):
            check_repository(self.root, self.product_facts)

    def test_unqualified_well_vintage_claim_fails(self):
        readme = self.root / "README.md"
        readme.write_text(
            readme.read_text(encoding="utf-8")
            + "\n`as_of` reconstructs well permit and well production history.\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ClaimCheckError, "forbidden well-data as_of claim"):
            check_repository(self.root, self.product_facts)

    def test_watchlist_math_drift_fails(self):
        recipe = self.root / "recipes" / "08_batch_watchlist_dataframe.py"
        recipe.write_text(
            recipe.read_text(encoding="utf-8").replace("4,320 calls", "5,760 calls"),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ClaimCheckError, "watchlist math"):
            check_repository(self.root, self.product_facts)

    def test_watchlist_batch_math_drift_fails(self):
        recipe = self.root / "recipes" / "08_batch_watchlist_dataframe.py"
        recipe.write_text(
            recipe.read_text(encoding="utf-8").replace(
                "schedule makes 720", "schedule makes 721"
            ),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ClaimCheckError, "watchlist math.*721 batch calls"):
            check_repository(self.root, self.product_facts)


if __name__ == "__main__":
    unittest.main()
