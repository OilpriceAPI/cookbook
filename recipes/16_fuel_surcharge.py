#!/usr/bin/env python3
"""Weekly fuel surcharge from the DOE (EIA) on-highway diesel index.

Most trucking surcharge tables key off the EIA weekly U.S. retail on-highway
diesel price (code DIESEL_RETAIL_USD; regional codes exist too). Give
/v1/fuel-surcharge/calculate your own schedule and it returns this week's
surcharge plus a weekly table, each row stamped with the EIA week it is for.

    percent   surcharge % = floor((diesel - base_price) / increment) * percent_per_increment
              (rounding=ceil counts a partial increment; rounding=exact does not band)
    per_mile  surcharge $/mile = (diesel - base_price) / mpg

Diesel at or below base_price is a 0 surcharge. The recipe re-does the
arithmetic locally so you can see there is nothing hidden, and checks the
current week against /v1/prices/latest for the same code.

    OILPRICEAPI_KEY=... python recipes/16_fuel_surcharge.py
    OILPRICEAPI_KEY=... python recipes/16_fuel_surcharge.py --region midwest --base 1.25 \\
        --increment 0.06 --percent 0.5

Regions: national, east-coast, midwest, gulf-coast, rocky-mountain,
west-coast, california. The fuel-surcharge routes carry no plan gate; a free
key works.

Real output, run 2026-11-10 01:26 UTC (default schedule: base 1.25, 0.05/step, 1%/step):

    EIA weekly U.S. retail on-highway diesel (DOE), USD/gallon (DIESEL_RETAIL_USD)
    as of week 2026-11-02  stale=False
    week         diesel  change surcharge  local
    2026-11-02    6.292  -0.060   100.00%  100.00% ok
    2026-10-26    6.352  +0.076   102.00%  102.00% ok
    2026-10-19    6.276  +0.097   100.00%  100.00% ok
    2026-10-12    6.179  -0.020    98.00%  98.00% ok
    /v1/prices/latest DIESEL_RETAIL_USD: 6.292 gallon (source eia_api, week 2026-11-02)

Free key: https://oilpriceapi.com/auth/signup?utm_source=github_examples&utm_medium=integration&utm_campaign=acq_q4
"""

from __future__ import annotations

import argparse
import math
import os
from decimal import Decimal

import requests

BASE = "https://api.oilpriceapi.com"


def local_percent(diesel: Decimal, base: Decimal, increment: Decimal, pct: Decimal) -> Decimal:
    """The floor-rounded percent construction, same as the API's default."""
    over = diesel - base
    if over <= 0:
        return Decimal("0")
    return (Decimal(math.floor(over / increment)) * pct).quantize(Decimal("0.01"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--region", default="national")
    parser.add_argument("--base", default="1.25", help="base diesel price, USD/gal")
    parser.add_argument("--increment", default="0.05", help="USD/gal per step")
    parser.add_argument("--percent", default="1", help="surcharge percent per step")
    parser.add_argument("--weeks", type=int, default=4)
    args = parser.parse_args()

    key = os.environ.get("OILPRICEAPI_KEY")
    if not key:
        raise SystemExit("Set OILPRICEAPI_KEY (a free key works).")
    headers = {"Authorization": f"Token {key}", "User-Agent": "oilpriceapi-cookbook/1"}

    resp = requests.get(
        f"{BASE}/v1/fuel-surcharge/calculate",
        headers=headers,
        params={
            "region": args.region,
            "base_price": args.base,
            "increment": args.increment,
            "percent_per_increment": args.percent,
            "weeks": args.weeks,
        },
        timeout=15,
    )
    if resp.status_code == 400:
        raise SystemExit(f"bad schedule: {resp.json()}")  # names every problem at once
    resp.raise_for_status()
    calc = resp.json()["data"]

    print(f"{calc['index']} ({calc['commodity_code']})")
    print(f"as of week {calc['as_of']}  stale={calc['stale']}")
    print(f"{'week':<11} {'diesel':>7} {'change':>7} {'surcharge':>9}  local")
    base, inc, pct = Decimal(args.base), Decimal(args.increment), Decimal(args.percent)
    for row in calc["weeks"]:
        mine = local_percent(Decimal(str(row["diesel_price"])), base, inc, pct)
        agree = "ok" if mine == Decimal(str(row["surcharge_percent"])).quantize(mine) else "DIFF"
        change = "" if row["diesel_change"] is None else f"{row['diesel_change']:+.3f}"
        print(
            f"{row['week_of']:<11} {row['diesel_price']:>7.3f} {change:>7} "
            f"{row['surcharge_percent']:>8.2f}%  {mine}% {agree}"
        )

    latest = requests.get(
        f"{BASE}/v1/prices/latest",
        headers=headers,
        params={"by_code": calc["commodity_code"]},
        timeout=15,
    )
    latest.raise_for_status()
    price = latest.json()["data"]
    print(
        f"/v1/prices/latest {price['code']}: {price['price']} {price['unit']} "
        f"(source {price['source']}, week {price['source_date']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
