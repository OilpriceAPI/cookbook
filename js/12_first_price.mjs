// First price from Node.js: built-in fetch, no dependencies (Node 18+).
//
// Without a key this calls the no-key demo (real, delayed prices; limited per
// IP per day). With OILPRICEAPI_KEY set it calls /v1/prices/latest and prints
// the quota headers the API sent with that same response.
//
//   node js/12_first_price.mjs
//   OILPRICEAPI_KEY=... node js/12_first_price.mjs
//
// Real output, keyed path, run 2026-11-10 01:23 UTC (quota values elided; they
// belong to the internal test account that ran it):
//   BRENT_CRUDE_USD           $92.37  as of 2026-11-10T01:11:00.000Z
//   WTI_USD                   $86.54  as of 2026-11-10T01:11:15.000Z
//   NATURAL_GAS_USD            $3.21  as of 2026-11-10T01:20:27.061Z
//   quota: <used>/<limit> used in the monthly window, state=<state>
//
// Free key: https://oilpriceapi.com/auth/signup?utm_source=github_examples&utm_medium=integration&utm_campaign=acq_q4

const BASE = "https://api.oilpriceapi.com";
const CODES = ["BRENT_CRUDE_USD", "WTI_USD", "NATURAL_GAS_USD"];

async function getJson(path, key) {
  const headers = { "User-Agent": "oilpriceapi-cookbook-js/1" };
  if (key) headers.Authorization = `Token ${key}`;
  const resp = await fetch(`${BASE}${path}`, {
    headers,
    signal: AbortSignal.timeout(10_000),
  });
  const body = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    // Errors carry {error: {code, message, request_id, docs}}. Keep the
    // request_id: support can trace the exact request from it.
    const err = typeof body.error === "object" && body.error ? body.error : {};
    const message = err.message ?? body.error ?? "unknown";
    throw new Error(
      `${resp.status} ${err.code ?? ""}: ${message} (request_id=${err.request_id ?? "?"})`,
    );
  }
  return { body, headers: resp.headers };
}

async function main() {
  const key = process.env.OILPRICEAPI_KEY;
  if (!key) {
    const { body } = await getJson("/v1/demo/prices/latest");
    for (const p of body.data.prices.slice(0, 5)) {
      console.log(`${p.code.padEnd(22)} ${String(p.price).padStart(9)}`);
    }
    console.log("(no-key demo; set OILPRICEAPI_KEY for the full API)");
    return;
  }

  let last;
  for (const code of CODES) {
    last = await getJson(`/v1/prices/latest?by_code=${encodeURIComponent(code)}`, key);
    const d = last.body.data;
    console.log(`${d.code.padEnd(22)} ${d.formatted.padStart(9)}  as of ${d.observed_at ?? d.created_at}`);
  }
  const h = last.headers;
  console.log(
    `quota: ${h.get("x-ratelimit-used")}/${h.get("x-ratelimit-limit")} used in the ` +
      `${h.get("x-ratelimit-window")} window, state=${h.get("x-ratelimit-state")}`,
  );
}

main().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
