# OilPriceAPI Cookbook

Runnable recipes for [OilPriceAPI](https://oilpriceapi.com) — oil, gas,
refined products, marine fuels, futures, and carbon prices through one REST
API. Every recipe in this repo was executed against production before it was
committed; the outputs shown are real.

```bash
python -m venv .venv && .venv/bin/pip install requests
.venv/bin/python recipes/01_first_price_no_key.py   # works with NO key
```

## Recipes

| #   | Recipe                                                                      | What it shows                                                                                  | Key needed |
| --- | --------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- | ---------- |
| 01  | [First price, no key](recipes/01_first_price_no_key.py)                     | Live demo prices for 37 commodities, zero signup                                               | none       |
| 02  | [Backtest without lookahead bias](recipes/02_backtest_without_lookahead.py) | `as_of` point-in-time history — see data as it was knowable on any date, revisions rolled back | $19+       |
| 03  | [Gas hub basis](recipes/03_gas_hub_basis.py)                                | Six US hubs priced as basis to Henry Hub, one call                                             | $19+       |
| 04  | [Bunker prices by port](recipes/04_bunker_prices_by_port.py)                | VLSFO/MGO for Singapore, Rotterdam, Santos via one code pattern                                | $19+       |
| 05  | [Deep history to 1997](recipes/05_deep_history_1997.py)                     | Arbitrary date ranges with `by_period` — Henry Hub at $2.27 in Dec 1997                        | $19+       |
| 06  | [Check series quality first](recipes/06_check_series_quality.py)            | Per-series quality grades computed from measured completeness/freshness                        | $19+       |
| 07  | [Futures curve structure](recipes/07_futures_curve_contango.py)             | Full Brent curve + contango/backwardation call in one request                                  | $99+       |

## Sample output (verified 2026-08-10)

**02 — the point-in-time view.** On 7 Aug 2026 US diesel printed 3.88, then
was revised to 3.90 at 22:10 UTC. With `as_of=2026-08-07T22:00:00Z` the API
serves what was knowable at that moment:

```
as-of 2026-08-07 22:00 UTC (what a backtest may see):
  2026-08-07T15:10  $3.88
```

**03 — hub basis.** Permian gas under the benchmark, as usual:

```
Henry Hub: $2.80/MMBtu
Waha (West Texas)      1.83   -0.93   since 2025-02-05
SoCal Citygate         3.85   +1.18   since 2026-04-11
Houston Ship Channel   2.23   -0.44   since 2026-07-14
```

**07 — curve structure:**

```
Brent curve: 14 contracts (backwardation)
front 2026-10  $82.27
back  2027-12  $72.84
```

## Keys and plans

- **Free** — 200 requests/month, latest prices: [sign up](https://oilpriceapi.com/auth/signup)
- **Developer $19/mo** — 10,000 requests, history + `as_of` + gas hubs
- **Professional $99/mo** — futures curves, marine port surface, spreads
- Full ladder: [oilpriceapi.com/pricing](https://oilpriceapi.com/pricing) ·
  Docs: [docs.oilpriceapi.com](https://docs.oilpriceapi.com) ·
  Agent spec: [llms-full.txt](https://api.oilpriceapi.com/llms-full.txt)

## Using an AI agent instead?

`npx oilpriceapi-mcp` gives Claude, Cursor, and other MCP clients 36 tools
over the same data — including the `as_of` vintage parameter and per-tool
plan requirements in the schemas.

## Data usage

Code here is MIT licensed. The data you retrieve is governed by the
[Data Usage Policy](https://www.oilpriceapi.com/legal/data-usage) — standard
plans cover internal workflows; public display or redistribution needs a review.
