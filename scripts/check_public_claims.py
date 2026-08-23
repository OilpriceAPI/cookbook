#!/usr/bin/env python3
"""Fail when cookbook claims drift from the canonical public contract."""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


PRODUCT_FACTS_URL = "https://api.oilpriceapi.com/product-facts.json"
PRODUCT_FACTS_SCHEMA_URL = (
    "https://api.oilpriceapi.com/schemas/product-facts-v1.schema.json"
)
PRODUCT_FACTS_SCHEMA_VERSION = "1.0.0"
API_ORIGIN = "https://api.oilpriceapi.com"
MAX_PRODUCT_FACTS_BYTES = 256 * 1024
PRODUCT_FACT_KEYS = {
    "root": frozenset(
        {
            "schemaVersion",
            "contractVersion",
            "reviewedAt",
            "reviewOwner",
            "schemaUrl",
            "canonicalUrl",
            "product",
            "offer",
            "catalog",
            "freshness",
            "dataRights",
            "developer",
        }
    ),
    "product": frozenset(
        {"name", "website", "apiBaseUrl", "documentationUrl", "description"}
    ),
    "offer": frozenset(
        {
            "trialDays",
            "trialRequests",
            "trialScope",
            "freeRequestsPerMonth",
            "freeRequestsWindow",
            "creditCardRequiredForTrial",
            "pricingUrl",
            "qualification",
        }
    ),
    "catalog": frozenset(
        {"publicWording", "exactCountPublished", "catalogUrl"}
    ),
    "freshness": frozenset({"publicWording", "fixedSitewideCadence"}),
    "dataRights": frozenset({"publicWording", "policyUrl"}),
    "developer": frozenset(
        {
            "authenticationHeader",
            "environmentVariable",
            "firstRequestMethod",
            "firstRequestPath",
            "firstRequestUrl",
            "demoRequestUrl",
        }
    ),
}
PUBLIC_TEXT_PATHS = (
    Path("README.md"),
    Path("recipes.json"),
)
ALLOWANCE_CLAIM_PATHS = (
    Path("README.md"),
    Path("recipes/01_first_price_no_key.py"),
    Path("recipes/10_resilient_client.py"),
)
SUPPORTED_AS_OF_ROUTES = (
    "/v1/prices/past_day",
    "/v1/prices/past_week",
    "/v1/prices/past_month",
    "/v1/prices/past_year",
)
AS_OF_COVERAGE_START = "2026-07-28"
ALLOWANCE_PATTERNS = (
    re.compile(
        r"(?P<count>\d[\d,]*)(?:\s*-\s*|\s+)"
        r"(?:api(?:\s*-\s*|\s+))?(?:requests?|calls?)"
        r"(?:\s*-\s*per\s*-\s*|\s+per\s+|\s*/\s*|\s+)"
        r"(?P<window>daily|monthly|day|month)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?P<count>\d[\d,]*)(?:\s*-\s*|\s+)"
        r"(?P<window>daily|monthly)"
        r"(?:\s*-\s*|\s+)(?:api(?:\s*-\s*|\s+))?(?:requests?|calls?)\b",
        re.IGNORECASE,
    ),
)
FREE_CONTEXT_PATTERN = re.compile(
    r"\bfree(?:[-\s]+(?:tier|plan|key|account))?\b", re.IGNORECASE
)
CLAUSE_BOUNDARY_PATTERN = re.compile(r"[.;]|\b(?:but|whereas|while)\b", re.IGNORECASE)
PLAN_HEADER_NAMES = frozenset({"plan", "tier"})
ALLOWANCE_HEADER_TERMS = frozenset(
    {"allowance", "allowances", "call", "calls", "quota", "request", "requests"}
)
WINDOW_HEADER_TERMS = {
    "day": frozenset({"day", "daily"}),
    "month": frozenset({"month", "monthly"}),
}
FORBIDDEN_BROAD_AS_OF_PATTERNS = (
    re.compile(r"\bany\s+history\s+endpoint\b", re.IGNORECASE),
    re.compile(r"\b(?:on|for)\s+any\s+date\b", re.IGNORECASE),
    re.compile(r"\breconstructs?\s+any\s+date\b", re.IGNORECASE),
)
WELL_DATA_PATTERN = re.compile(r"\bwell\s+(?:permits?|production)\b", re.IGNORECASE)
AS_OF_PATTERN = re.compile(r"\bas[_-]of\b|\bas of\b", re.IGNORECASE)
WATCHLIST_MATH_PATTERN = re.compile(
    r"Polling\s+(?P<codes>\w+)\s+codes\s+separately\s+each\s+hour\s+makes\s+"
    r"(?P<calls>[\d,]+)\s+calls\s+in\s+a\s+30-day\s+month;\s+batching\s+the\s+same\s+"
    r"schedule\s+makes\s+(?P<batch_calls>[\d,]+)",
    re.IGNORECASE,
)
NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}


class ClaimCheckError(RuntimeError):
    """Raised when a public cookbook claim disagrees with its contract."""


def _reject_duplicate_fields(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ClaimCheckError(f"product facts contain duplicate JSON field {key!r}")
        result[key] = value
    return result


def _exact_object(value: Any, path: str, expected_keys: frozenset[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ClaimCheckError(f"{path} must be a JSON object")

    actual_keys = set(value)
    missing = sorted(expected_keys - actual_keys)
    unexpected = sorted(actual_keys - expected_keys)
    if missing:
        raise ClaimCheckError(f"{path} missing fields: {', '.join(missing)}")
    if unexpected:
        raise ClaimCheckError(f"{path} has unexpected fields: {', '.join(unexpected)}")
    return value


def _nonempty_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ClaimCheckError(f"{path} must be a non-empty string")
    return value


def _positive_integer(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ClaimCheckError(f"{path} must be a positive integer")
    return value


def _boolean(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        raise ClaimCheckError(f"{path} must be a boolean")
    return value


def _https_url(value: Any, path: str) -> str:
    url = _nonempty_string(value, path)
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise ClaimCheckError(f"{path} must be an HTTPS URL without credentials")
    return url


def _validate_provenance(product_facts: dict[str, Any]) -> None:
    contract_version = _nonempty_string(
        product_facts["contractVersion"], "contractVersion"
    )
    reviewed_at = _nonempty_string(product_facts["reviewedAt"], "reviewedAt")
    if contract_version != reviewed_at:
        raise ClaimCheckError(
            "product facts provenance requires contractVersion and reviewedAt to match"
        )

    try:
        reviewed_date = date.fromisoformat(reviewed_at)
    except (TypeError, ValueError) as error:
        raise ClaimCheckError(
            "product facts provenance dates must be valid ISO dates"
        ) from error
    if reviewed_date.isoformat() != reviewed_at:
        raise ClaimCheckError("product facts provenance dates must use YYYY-MM-DD")
    if reviewed_date > date.today():
        raise ClaimCheckError("product facts provenance cannot be in the future")


def validate_product_facts(product_facts: dict[str, Any]) -> None:
    """Validate the exact released product-facts contract before using any claim."""

    if not isinstance(product_facts, dict):
        raise ClaimCheckError("product facts must be a JSON object")
    if product_facts.get("schemaVersion") != PRODUCT_FACTS_SCHEMA_VERSION:
        raise ClaimCheckError(
            f"schemaVersion must be exactly {PRODUCT_FACTS_SCHEMA_VERSION}"
        )

    root = _exact_object(product_facts, "product facts", PRODUCT_FACT_KEYS["root"])
    sections = {
        name: _exact_object(root[name], name, PRODUCT_FACT_KEYS[name])
        for name in ("product", "offer", "catalog", "freshness", "dataRights", "developer")
    }

    _validate_provenance(root)
    _nonempty_string(root["reviewOwner"], "reviewOwner")
    if root["schemaUrl"] != PRODUCT_FACTS_SCHEMA_URL:
        raise ClaimCheckError(f"schemaUrl must be exactly {PRODUCT_FACTS_SCHEMA_URL}")
    if root["canonicalUrl"] != PRODUCT_FACTS_URL:
        raise ClaimCheckError(f"canonicalUrl must be exactly {PRODUCT_FACTS_URL}")

    product = sections["product"]
    for field in ("name", "description"):
        _nonempty_string(product[field], f"product.{field}")
    for field in ("website", "apiBaseUrl", "documentationUrl"):
        _https_url(product[field], f"product.{field}")
    if product["apiBaseUrl"] != API_ORIGIN:
        raise ClaimCheckError(f"product.apiBaseUrl must be exactly {API_ORIGIN}")

    offer = sections["offer"]
    # The released v1 field retains its original name for compatibility. The
    # companion window is authoritative, so this is 50/day when the window is
    # ``day``; consumers must never infer ``month`` from the field name.
    for field in ("trialDays", "trialRequests", "freeRequestsPerMonth"):
        _positive_integer(offer[field], f"offer.{field}")
    for field in ("trialScope", "qualification"):
        _nonempty_string(offer[field], f"offer.{field}")
    _boolean(offer["creditCardRequiredForTrial"], "offer.creditCardRequiredForTrial")
    _https_url(offer["pricingUrl"], "offer.pricingUrl")
    if offer["freeRequestsWindow"] not in {"day", "month"}:
        raise ClaimCheckError("offer.freeRequestsWindow must be day or month")

    catalog = sections["catalog"]
    _nonempty_string(catalog["publicWording"], "catalog.publicWording")
    _boolean(catalog["exactCountPublished"], "catalog.exactCountPublished")
    _https_url(catalog["catalogUrl"], "catalog.catalogUrl")

    freshness = sections["freshness"]
    _nonempty_string(freshness["publicWording"], "freshness.publicWording")
    cadence = freshness["fixedSitewideCadence"]
    if cadence is not None:
        _nonempty_string(cadence, "freshness.fixedSitewideCadence")

    data_rights = sections["dataRights"]
    _nonempty_string(data_rights["publicWording"], "dataRights.publicWording")
    _https_url(data_rights["policyUrl"], "dataRights.policyUrl")

    developer = sections["developer"]
    for field in ("authenticationHeader", "environmentVariable", "firstRequestPath"):
        _nonempty_string(developer[field], f"developer.{field}")
    if developer["authenticationHeader"] != "Authorization: Token YOUR_API_KEY":
        raise ClaimCheckError("developer.authenticationHeader is not the reviewed contract")
    if developer["environmentVariable"] != "OILPRICEAPI_KEY":
        raise ClaimCheckError("developer.environmentVariable is not the reviewed contract")
    if developer["firstRequestMethod"] != "GET":
        raise ClaimCheckError("developer.firstRequestMethod must be GET")
    first_path = developer["firstRequestPath"]
    if not first_path.startswith("/v1/") or ".." in first_path:
        raise ClaimCheckError("developer.firstRequestPath must be a canonical /v1/ path")
    expected_first_url = f"{API_ORIGIN}{first_path}"
    if developer["firstRequestUrl"] != expected_first_url:
        raise ClaimCheckError(
            "developer.firstRequestUrl must match apiBaseUrl and firstRequestPath"
        )
    if developer["demoRequestUrl"] != f"{API_ORIGIN}/v1/demo/prices":
        raise ClaimCheckError("developer.demoRequestUrl is not the reviewed contract")


def load_product_facts(source: str | Path = PRODUCT_FACTS_URL) -> dict[str, Any]:
    """Load product facts from the canonical URL or a deterministic test fixture."""

    try:
        remote = not isinstance(source, Path) and str(source).startswith(
            ("http://", "https://")
        )
        if not remote:
            payload = Path(source).read_text(encoding="utf-8")
        else:
            if str(source) != PRODUCT_FACTS_URL:
                raise ClaimCheckError(
                    f"product facts source URL must be exactly {PRODUCT_FACTS_URL}"
                )
            request = Request(
                str(source),
                headers={"User-Agent": "oilpriceapi-cookbook-claim-check/1"},
            )
            with urlopen(request, timeout=15) as response:
                if response.geturl() != PRODUCT_FACTS_URL:
                    raise ClaimCheckError(
                        "canonical product facts request redirected away from its reviewed URL"
                    )
                raw_payload = response.read(MAX_PRODUCT_FACTS_BYTES + 1)
                if len(raw_payload) > MAX_PRODUCT_FACTS_BYTES:
                    raise ClaimCheckError("product facts payload exceeds the reviewed size limit")
                payload = raw_payload.decode("utf-8")
        facts = json.loads(payload, object_pairs_hook=_reject_duplicate_fields)
    except ClaimCheckError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ClaimCheckError(f"could not load product facts from {source}: {error}") from error

    validate_product_facts(facts)
    return facts


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as error:
        raise ClaimCheckError(f"could not read {path}: {error}") from error


def _public_sources(root: Path) -> dict[Path, str]:
    paths = [root / path for path in PUBLIC_TEXT_PATHS]
    paths.extend(sorted((root / "recipes").rglob("*.py")))
    return {path.relative_to(root): _read(path) for path in paths}


def _canonical_allowance(product_facts: dict[str, Any]) -> tuple[int, str]:
    offer = product_facts["offer"]
    return offer["freeRequestsPerMonth"], offer["freeRequestsWindow"]


def _parse_count(value: str) -> int:
    normalized = value.lower()
    if normalized in NUMBER_WORDS:
        return NUMBER_WORDS[normalized]
    return int(normalized.replace(",", ""))


def _normalize_window(value: str) -> str:
    return "day" if value.lower() in {"day", "daily"} else "month"


def _inline_free_allowance_claims(text: str) -> list[tuple[int, str]]:
    claims: list[tuple[int, str]] = []
    prose = " ".join(
        line.strip() for line in text.splitlines() if not line.lstrip().startswith("|")
    )
    for clause_group in prose.splitlines():
        if not FREE_CONTEXT_PATTERN.search(clause_group):
            continue
        seen_spans: set[tuple[int, int]] = set()
        for pattern in ALLOWANCE_PATTERNS:
            for match in pattern.finditer(clause_group):
                if match.span() in seen_spans:
                    continue
                seen_spans.add(match.span())
                boundaries = list(CLAUSE_BOUNDARY_PATTERN.finditer(clause_group))
                clause_start = max(
                    (boundary.end() for boundary in boundaries if boundary.end() <= match.start()),
                    default=0,
                )
                clause_end = min(
                    (
                        boundary.start()
                        for boundary in boundaries
                        if boundary.start() >= match.end()
                    ),
                    default=len(clause_group),
                )
                if not FREE_CONTEXT_PATTERN.search(
                    clause_group[clause_start:clause_end]
                ):
                    continue
                claims.append(
                    (_parse_count(match.group("count")), _normalize_window(match.group("window")))
                )
    return claims


def _markdown_cells(line: str) -> list[str] | None:
    stripped = line.strip()
    if "|" not in stripped:
        return None
    return [cell.strip() for cell in stripped.strip("|").split("|")]


def _normalized_table_cell(cell: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", cell.lower()))


def _is_table_divider(cells: list[str]) -> bool:
    return bool(cells) and all(
        re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in cells
    )


def _allowance_header_window(cell: str) -> str | None:
    terms = set(_normalized_table_cell(cell).split())
    if not terms & ALLOWANCE_HEADER_TERMS:
        return None
    for window, window_terms in WINDOW_HEADER_TERMS.items():
        if terms & window_terms:
            return window
    return None


def _table_free_allowance_claims(text: str) -> list[tuple[int, str]]:
    lines = text.splitlines()
    claims: list[tuple[int, str]] = []

    for index in range(len(lines) - 2):
        header = _markdown_cells(lines[index])
        divider = _markdown_cells(lines[index + 1])
        if not header or not divider or len(header) != len(divider):
            continue
        if not _is_table_divider(divider):
            continue

        plan_columns = [
            column
            for column, cell in enumerate(header)
            if _normalized_table_cell(cell) in PLAN_HEADER_NAMES
        ]
        allowance_columns = {
            column: window
            for column, cell in enumerate(header)
            if (window := _allowance_header_window(cell)) is not None
        }
        if not plan_columns or not allowance_columns:
            continue

        for row_line in lines[index + 2 :]:
            row = _markdown_cells(row_line)
            if not row or len(row) != len(header) or _is_table_divider(row):
                break
            if not any(
                FREE_CONTEXT_PATTERN.search(row[column]) for column in plan_columns
            ):
                continue
            for column in allowance_columns:
                if match := re.search(r"(?<!\d)(?P<count>\d[\d,]*)(?!\d)", row[column]):
                    claims.append(
                        (_parse_count(match.group("count")), allowance_columns[column])
                    )

    return claims


def _check_allowance(
    sources: dict[Path, str], allowance: tuple[int, str], errors: list[str]
) -> None:
    expected_count, expected_window = allowance
    paths_with_claims: set[Path] = set()
    for relative_path, text in sources.items():
        claims = _inline_free_allowance_claims(text) + _table_free_allowance_claims(text)
        if claims:
            paths_with_claims.add(relative_path)
        for count, window in claims:
            if (count, window) != allowance:
                errors.append(
                    f"{relative_path}: canonical free allowance is {expected_count} "
                    f"requests/{expected_window} but local claim is {count} requests/{window}"
                )

    for relative_path in ALLOWANCE_CLAIM_PATHS:
        if relative_path not in paths_with_claims:
            errors.append(
                f"{relative_path}: missing explicit free requests/{expected_window} claim"
            )


def _check_quota_recipe_contract(root: Path, errors: list[str]) -> None:
    relative_path = Path("recipes/10_resilient_client.py")
    recipe = _read(root / relative_path)
    for forbidden in ("/v1/dashboard", "current_month"):
        if forbidden in recipe:
            errors.append(f"{relative_path}: legacy quota surface {forbidden!r} is forbidden")
    for header in (
        "X-RateLimit-Limit",
        "X-RateLimit-Remaining",
        "X-RateLimit-Used",
        "X-RateLimit-Window",
        "X-RateLimit-State",
        "X-RateLimit-Reset",
    ):
        if header not in recipe:
            errors.append(f"{relative_path}: missing quota recovery header {header}")


def _check_forbidden_as_of_claims(sources: dict[Path, str], errors: list[str]) -> None:
    for path, text in sources.items():
        for pattern in FORBIDDEN_BROAD_AS_OF_PATTERNS:
            if match := pattern.search(text):
                errors.append(
                    f"{path}: forbidden broad as_of claim {match.group(0)!r}"
                )

        for sentence in re.split(r"(?<=[.!?])\s+|\n+", text):
            if AS_OF_PATTERN.search(sentence) and WELL_DATA_PATTERN.search(sentence):
                errors.append(f"{path}: forbidden well-data as_of claim {sentence.strip()!r}")


def _check_as_of_contract(root: Path, errors: list[str]) -> None:
    recipe_path = Path("recipes/02_backtest_without_lookahead.py")
    recipe = _read(root / recipe_path)
    recipe_routes = set(re.findall(r"/v1/prices/[a-z_]+", recipe))
    supported_routes = set(SUPPORTED_AS_OF_ROUTES)
    if recipe_routes != supported_routes:
        errors.append(
            f"{recipe_path}: as_of routes must be exactly {sorted(supported_routes)}; "
            f"found {sorted(recipe_routes)}"
        )
    if not re.search(r'["\']interval["\']\s*:\s*["\']raw["\']', recipe):
        errors.append(f"{recipe_path}: request params must set interval to raw")
    if "interval=raw" not in recipe:
        errors.append(f"{recipe_path}: public copy must state interval=raw")
    if AS_OF_COVERAGE_START not in recipe:
        errors.append(
            f"{recipe_path}: public copy must state correction coverage starts "
            f"{AS_OF_COVERAGE_START}"
        )

    readme = _read(root / "README.md")
    for marker in (*SUPPORTED_AS_OF_ROUTES, "interval=raw", AS_OF_COVERAGE_START):
        if marker not in readme:
            errors.append(f"README.md: missing as_of contract marker {marker!r}")


def _watchlist_size(recipe: str, path: Path) -> int:
    try:
        tree = ast.parse(recipe, filename=str(path))
    except SyntaxError as error:
        raise ClaimCheckError(f"could not parse {path}: {error}") from error
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        is_watchlist = any(
            isinstance(target, ast.Name) and target.id == "WATCHLIST"
            for target in node.targets
        )
        if not is_watchlist:
            continue
        if isinstance(node.value, (ast.List, ast.Tuple)):
            return len(node.value.elts)
    raise ClaimCheckError(f"{path}: WATCHLIST must remain a literal list or tuple")


def _check_watchlist_math(root: Path, errors: list[str]) -> None:
    relative_path = Path("recipes/08_batch_watchlist_dataframe.py")
    recipe = _read(root / relative_path)
    actual_codes = _watchlist_size(recipe, relative_path)
    match = WATCHLIST_MATH_PATTERN.search(recipe)
    if not match:
        errors.append(f"{relative_path}: missing checkable 30-day watchlist math claim")
        return

    claimed_codes = _parse_count(match.group("codes"))
    claimed_calls = _parse_count(match.group("calls"))
    claimed_batch_calls = _parse_count(match.group("batch_calls"))
    expected_calls = actual_codes * 24 * 30
    expected_batch_calls = 24 * 30
    if (
        claimed_codes != actual_codes
        or claimed_calls != expected_calls
        or claimed_batch_calls != expected_batch_calls
    ):
        errors.append(
            f"{relative_path}: watchlist math claims {claimed_codes} codes and "
            f"{claimed_calls:,} separate calls plus {claimed_batch_calls:,} batch calls; "
            f"literal WATCHLIST has {actual_codes} codes and implies {expected_calls:,} "
            f"separate calls plus {expected_batch_calls:,} batch calls"
        )


def check_repository(root: Path, product_facts: dict[str, Any]) -> None:
    """Validate all guarded public claims, raising one aggregated error."""

    root = root.resolve()
    errors: list[str] = []
    validate_product_facts(product_facts)
    allowance = _canonical_allowance(product_facts)
    sources = _public_sources(root)
    _check_allowance(sources, allowance, errors)
    _check_forbidden_as_of_claims(sources, errors)
    _check_as_of_contract(root, errors)
    _check_watchlist_math(root, errors)
    _check_quota_recipe_contract(root, errors)
    if errors:
        raise ClaimCheckError("public claim check failed:\n- " + "\n- ".join(errors))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="cookbook repository root",
    )
    parser.add_argument(
        "--product-facts",
        default=PRODUCT_FACTS_URL,
        help="canonical product-facts URL or a local JSON fixture",
    )
    args = parser.parse_args()

    try:
        product_facts = load_product_facts(args.product_facts)
        check_repository(args.root, product_facts)
    except ClaimCheckError as error:
        print(error, file=sys.stderr)
        return 1

    print(
        "public claims OK: "
        f"freeRequestLimit={product_facts['offer']['freeRequestsPerMonth']}; "
        f"freeRequestWindow={product_facts['offer']['freeRequestsWindow']}; "
        f"contractVersion={product_facts.get('contractVersion', 'unreported')}; "
        f"reviewedAt={product_facts.get('reviewedAt', 'unreported')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
