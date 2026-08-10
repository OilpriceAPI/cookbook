import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.check_public_claims import ClaimCheckError, check_repository, load_product_facts


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


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
