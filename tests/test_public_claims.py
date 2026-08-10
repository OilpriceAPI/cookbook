import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.check_public_claims import ClaimCheckError, check_repository, load_product_facts


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
STALE_FREE_ALLOWANCE_VARIANTS = (
    "Free tier includes 200 requests per month.",
    "Free plan includes 200 API calls/month.",
    "Free account includes 200-API-calls-per-month.",
    "Free key includes 200 requests-per-month.",
    "Free tier includes 200 monthly requests.",
)


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
            "canonical free allowance is 51.*local claim is 50",
        ):
            check_repository(self.root, changed_facts)

    def test_new_stale_allowance_claim_fails(self):
        recipe = self.root / "recipes" / "09_agent_tool.py"
        recipe.write_text(
            recipe.read_text(encoding="utf-8") + "\n# Free key: 200 requests/month.\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(
            ClaimCheckError,
            "canonical free allowance is 50.*local claim is 200",
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
                    "canonical free allowance is 50.*local claim is 200",
                ):
                    check_repository(self.root, self.product_facts)

    def test_isolated_stale_free_table_value_fails(self):
        readme = self.root / "README.md"
        readme.write_text(
            readme.read_text(encoding="utf-8")
            + "\n| Plan | API calls / month | Price |\n"
            + "| --- | ---: | ---: |\n"
            + "| Free | 200 | $0 |\n"
            + "| Developer | 10,000 | $19 |\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(
            ClaimCheckError,
            "canonical free allowance is 50.*local claim is 200",
        ):
            check_repository(self.root, self.product_facts)

    def test_current_free_and_paid_allowances_pass(self):
        readme = self.root / "README.md"
        readme.write_text(
            readme.read_text(encoding="utf-8")
            + "\nFree remains at 50 requests/month, while Developer includes "
            + "10,000 requests per month at $19. Professional includes "
            + "100,000 API calls/month at $99.\n"
            + "\n| Tier | Monthly requests | Price |\n"
            + "| --- | ---: | ---: |\n"
            + "| Free | **50** | $0 |\n"
            + "| Developer | 10,000 | $19 |\n"
            + "| Professional | 100,000 | $99 |\n",
            encoding="utf-8",
        )

        check_repository(self.root, self.product_facts)

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


if __name__ == "__main__":
    unittest.main()
