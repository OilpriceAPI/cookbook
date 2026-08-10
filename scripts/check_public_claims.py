#!/usr/bin/env python3
"""Fail when cookbook claims drift from the canonical public contract."""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


PRODUCT_FACTS_URL = "https://api.oilpriceapi.com/product-facts.json"
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
        r"(?:\s*-\s*per\s*-\s*|\s+per\s+|\s*/\s*|\s+)month(?:ly)?\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?P<count>\d[\d,]*)(?:\s*-\s*|\s+)monthly"
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
MONTH_HEADER_TERMS = frozenset({"month", "monthly"})
FORBIDDEN_BROAD_AS_OF_PATTERNS = (
    re.compile(r"\bany\s+history\s+endpoint\b", re.IGNORECASE),
    re.compile(r"\b(?:on|for)\s+any\s+date\b", re.IGNORECASE),
    re.compile(r"\breconstructs?\s+any\s+date\b", re.IGNORECASE),
)
WELL_DATA_PATTERN = re.compile(r"\bwell\s+(?:permits?|production)\b", re.IGNORECASE)
AS_OF_PATTERN = re.compile(r"\bas[_-]of\b|\bas of\b", re.IGNORECASE)
WATCHLIST_MATH_PATTERN = re.compile(
    r"Polling\s+(?P<codes>\w+)\s+codes\s+separately\s+each\s+hour\s+makes\s+"
    r"(?P<calls>[\d,]+)\s+calls\s+in\s+a\s+30-day\s+month",
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


def load_product_facts(source: str | Path = PRODUCT_FACTS_URL) -> dict[str, Any]:
    """Load product facts from the canonical URL or a deterministic test fixture."""

    try:
        if isinstance(source, Path) or not str(source).startswith(("http://", "https://")):
            payload = Path(source).read_text(encoding="utf-8")
        else:
            request = Request(
                str(source),
                headers={"User-Agent": "oilpriceapi-cookbook-claim-check/1"},
            )
            with urlopen(request, timeout=15) as response:
                payload = response.read().decode("utf-8")
        facts = json.loads(payload)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ClaimCheckError(f"could not load product facts from {source}: {error}") from error

    if not isinstance(facts, dict):
        raise ClaimCheckError("product facts must be a JSON object")
    return facts


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as error:
        raise ClaimCheckError(f"could not read {path}: {error}") from error


def _public_sources(root: Path) -> dict[Path, str]:
    paths = [root / path for path in PUBLIC_TEXT_PATHS]
    paths.extend(sorted((root / "recipes").glob("*.py")))
    return {path.relative_to(root): _read(path) for path in paths}


def _canonical_allowance(product_facts: dict[str, Any]) -> int:
    try:
        allowance = product_facts["offer"]["freeRequestsPerMonth"]
    except (KeyError, TypeError) as error:
        raise ClaimCheckError("product facts omit offer.freeRequestsPerMonth") from error
    if isinstance(allowance, bool) or not isinstance(allowance, int) or allowance <= 0:
        raise ClaimCheckError("offer.freeRequestsPerMonth must be a positive integer")
    return allowance


def _parse_count(value: str) -> int:
    normalized = value.lower()
    if normalized in NUMBER_WORDS:
        return NUMBER_WORDS[normalized]
    return int(normalized.replace(",", ""))


def _inline_free_allowance_claims(text: str) -> list[int]:
    claims: list[int] = []
    for line in text.splitlines():
        if line.lstrip().startswith("|") or not FREE_CONTEXT_PATTERN.search(line):
            continue
        seen_spans: set[tuple[int, int]] = set()
        for pattern in ALLOWANCE_PATTERNS:
            for match in pattern.finditer(line):
                if match.span() in seen_spans:
                    continue
                seen_spans.add(match.span())
                boundaries = list(CLAUSE_BOUNDARY_PATTERN.finditer(line))
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
                    default=len(line),
                )
                if not FREE_CONTEXT_PATTERN.search(line[clause_start:clause_end]):
                    continue
                claims.append(_parse_count(match.group("count")))
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


def _is_monthly_allowance_header(cell: str) -> bool:
    terms = set(_normalized_table_cell(cell).split())
    return bool(terms & ALLOWANCE_HEADER_TERMS) and bool(terms & MONTH_HEADER_TERMS)


def _table_free_allowance_claims(text: str) -> list[int]:
    lines = text.splitlines()
    claims: list[int] = []

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
        allowance_columns = [
            column
            for column, cell in enumerate(header)
            if _is_monthly_allowance_header(cell)
        ]
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
                    claims.append(_parse_count(match.group("count")))

    return claims


def _check_allowance(
    sources: dict[Path, str], allowance: int, errors: list[str]
) -> None:
    paths_with_claims: set[Path] = set()
    for relative_path, text in sources.items():
        claims = _inline_free_allowance_claims(text) + _table_free_allowance_claims(text)
        if claims:
            paths_with_claims.add(relative_path)
        for claim in claims:
            if claim != allowance:
                errors.append(
                    f"{relative_path}: canonical free allowance is {allowance} "
                    f"requests/month but local claim is {claim}"
                )

    for relative_path in ALLOWANCE_CLAIM_PATHS:
        if relative_path not in paths_with_claims:
            errors.append(f"{relative_path}: missing explicit free requests/month claim")


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
    expected_calls = actual_codes * 24 * 30
    if claimed_codes != actual_codes or claimed_calls != expected_calls:
        errors.append(
            f"{relative_path}: watchlist math claims {claimed_codes} codes and "
            f"{claimed_calls:,} calls; literal WATCHLIST has {actual_codes} codes and "
            f"implies {expected_calls:,} calls"
        )


def check_repository(root: Path, product_facts: dict[str, Any]) -> None:
    """Validate all guarded public claims, raising one aggregated error."""

    root = root.resolve()
    errors: list[str] = []
    allowance = _canonical_allowance(product_facts)
    sources = _public_sources(root)
    _check_allowance(sources, allowance, errors)
    _check_forbidden_as_of_claims(sources, errors)
    _check_as_of_contract(root, errors)
    _check_watchlist_math(root, errors)
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
        f"freeRequestsPerMonth={product_facts['offer']['freeRequestsPerMonth']}; "
        f"contractVersion={product_facts.get('contractVersion', 'unreported')}; "
        f"reviewedAt={product_facts.get('reviewedAt', 'unreported')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
