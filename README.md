# OilPriceAPI Cookbook

Runnable recipes for [OilPriceAPI](https://oilpriceapi.com), a REST API for
oil, natural gas, refined products, marine fuels, futures, and carbon prices.
The base URL is `https://api.oilpriceapi.com` and authentication is a single
header: `Authorization: Token YOUR_KEY`. Every recipe in this repo was
executed against production before it was committed; the outputs shown are
real and dated.

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python recipes/01_first_price_no_key.py   # works with NO key
```

Machine-readable index: [`recipes.json`](recipes.json) · Agent spec:
[llms-full.txt](https://api.oilpriceapi.com/llms-full.txt)

## Using an AI agent? Start here

`npx oilpriceapi-mcp` gives Claude, Cursor, and any MCP client **36 tools**
over the same data — point-in-time history, gas hubs, futures curves — with
each tool's plan requirement stated in its schema. Recipe 09 shows both the
MCP config and a framework-free tool function for OpenAI/LangChain agents.

## Recipes, grouped by job

**Get a price**

| #   | Recipe                                                                                                            | Key   |
| --- | ----------------------------------------------------------------------------------------------------------------- | ----- |
| 01  | [First price, no key](recipes/01_first_price_no_key.py) — the no-key demo serves 37 codes from the full catalogue | none  |
| 10  | [A production client in 40 lines](recipes/10_resilient_client.py) — error envelope, 429 backoff, quota check      | free+ |
| 09  | [Give an AI agent prices](recipes/09_agent_tool.py) — tool function + OpenAI schema + MCP config                  | free+ |

**Trust it**

| #   | Recipe                                                                                                                          | Key  |
| --- | ------------------------------------------------------------------------------------------------------------------------------- | ---- |
| 06  | [Check series quality first](recipes/06_check_series_quality.py) — per-series grades from measured completeness/freshness       | $19+ |
| 02  | [Backtest without lookahead bias](recipes/02_backtest_without_lookahead.py) — `as_of` reconstructs supported raw-window vintages | $19+ |

**Widen it — same key, your second call**

Already pulling one benchmark on a schedule? These are the natural next calls.

| #   | Recipe                                                                                                                                        | Key       |
| --- | --------------------------------------------------------------------------------------------------------------------------------------------- | --------- |
| 08  | [Whole watchlist in one request](recipes/08_batch_watchlist_dataframe.py) — batch endpoint, pandas, CSV; one call = one request against quota | $19+      |
| 03  | [Gas hub basis](recipes/03_gas_hub_basis.py) — six US hubs vs Henry Hub in one call                                                           | $19+      |
| 04  | [Bunker prices by port](recipes/04_bunker_prices_by_port.py) — Singapore, Rotterdam, Santos; flat codes at $19, port surface at $99           | $19 / $99 |

**Go deeper**

| #   | Recipe                                                                                                           | Key  |
| --- | ---------------------------------------------------------------------------------------------------------------- | ---- |
| 05  | [Deep history to 1997](recipes/05_deep_history_1997.py) — arbitrary ranges via `by_period`                       | $19+ |
| 07  | [Futures curve structure](recipes/07_futures_curve_contango.py) — full Brent curve + contango/backwardation call | $99+ |

## Sample output (verified 2026-08-10)

**02 — the point-in-time view.** On 7 Aug 2026 US diesel printed 3.88, then
was revised to 3.90 at 22:10 UTC. The same row, both ways:

```
as-of 2026-08-07 22:00 UTC (what a backtest may see):
  2026-08-07T15:10  $3.88
same rows as known today (revisions applied):
  2026-08-07T15:10  $3.9
```

`as_of` is currently supported only on `/v1/prices/past_day`,
`/v1/prices/past_week`, `/v1/prices/past_month`, and
`/v1/prices/past_year`, with `interval=raw`. Rows observed after the requested
instant are absent. Correction rollback covers revisions recorded from
2026-07-28 forward; it is not a claim of earlier correction-vintage coverage.

**03 — hub basis.** Permian gas under the benchmark, as usual:

```
Henry Hub: $2.80/MMBtu
Waha (West Texas)      1.83   -0.93   since 2025-02-05
Houston Ship Channel   2.23   -0.44   since 2026-07-14
```

**08 — one batch call, six surfaces:**

```
           code  price currency           unit
BRENT_CRUDE_USD  86.17      USD         barrel
VLSFO_BRSSZ_USD 791.50      USD     metric_ton
  EU_CARBON_EUR  83.04      EUR metric_ton_co2
```

## Keys and plans

The free tier serves **latest prices only** (50 requests/month) — history,
`as_of`, and gas hubs are the $19 unlock; futures curves and the marine port
surface are the $99 unlock. Prices as of 2026-08-10; the reviewed source for
plan facts is
[product-facts.json](https://api.oilpriceapi.com/product-facts.json) and the
current ladder is at [oilpriceapi.com/pricing](https://oilpriceapi.com/pricing).
The live contract currently reports `contractVersion` and `reviewedAt` as
2026-07-18; this cookbook reports that metadata as-is rather than inferring a
new version from the later verification date.
[Sign up](https://oilpriceapi.com/auth/signup) ·
[Docs](https://docs.oilpriceapi.com)

## License and data usage

The code in this repository is MIT licensed. **The data the API returns is
not** — it is governed by the
[Data Usage Policy](https://www.oilpriceapi.com/legal/data-usage): standard
plans cover internal workflows; public display or redistribution needs review.
