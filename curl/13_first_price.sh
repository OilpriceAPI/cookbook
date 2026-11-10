#!/usr/bin/env bash
# Prices from the shell: curl + jq, nothing else.
#
# Without a key: the no-key demo (real, delayed prices; limited per IP per day).
# With OILPRICEAPI_KEY: up to 20 codes in one /v1/prices/latest call, counted as
# one request, plus the quota headers from that same response.
#
#   bash curl/13_first_price.sh
#   OILPRICEAPI_KEY=... bash curl/13_first_price.sh
#
# Real output, keyed path, run 2026-11-10 01:23 UTC (limit/used lines elided;
# they belong to the internal test account that ran it):
#   BRENT_CRUDE_USD    92.37  barrel  as of 2026-11-10T01:11:00.000Z
#   WTI_USD            86.54  barrel  as of 2026-11-10T01:11:15.000Z
#   DIESEL_RETAIL_USD  6.292  gallon  as of 2026-11-02T12:00:00.000Z
#   x-ratelimit-window: monthly
#
# Free key: https://oilpriceapi.com/auth/signup?utm_source=github_examples&utm_medium=integration&utm_campaign=acq_q4
set -euo pipefail

BASE="https://api.oilpriceapi.com"
UA="oilpriceapi-cookbook-curl/1"

if [[ -z "${OILPRICEAPI_KEY:-}" ]]; then
  # --fail-with-body keeps the JSON error envelope visible on a 4xx.
  curl -sS --fail-with-body -A "$UA" "$BASE/v1/demo/prices/latest" |
    jq -r '.data.prices[:5][] | "\(.code)\t\(.price)"'
  echo "(no-key demo; set OILPRICEAPI_KEY for the full API)"
  exit 0
fi

headers="$(mktemp)"
trap 'rm -f "$headers"' EXIT

# The key goes in a header read from the environment, never in the URL.
curl -sS --fail-with-body -A "$UA" -D "$headers" \
  -H "Authorization: Token ${OILPRICEAPI_KEY}" \
  "$BASE/v1/prices/latest?by_code=BRENT_CRUDE_USD,WTI_USD,DIESEL_RETAIL_USD" |
  jq -r '.data.prices[] | "\(.code)\t\(.price)\t\(.unit)\tas of \(.observed_at // .created_at)"'

grep -i '^x-ratelimit-\(limit\|used\|window\|state\)' "$headers" | tr -d '\r'
