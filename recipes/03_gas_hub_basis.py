"""US natural gas hub basis — is Permian gas trading under Henry Hub?

Regional US gas trades at a basis (difference) to the Henry Hub benchmark.
Waha (West Texas) is routinely NEGATIVE — pipeline-constrained Permian gas
can trade dollars under the benchmark, and has traded below zero outright.

One endpoint serves six hubs, each priced as basis to Henry Hub for the
same gas day: Waha, SoCal Citygate, Chicago Citygate, Algonquin Citygate,
Eastern Gas South (formerly Dominion South), Houston Ship Channel.

    OILPRICEAPI_KEY=... python 03_gas_hub_basis.py

Requires a paid key (Developer, $19/mo and up).
"""

import os

import requests

resp = requests.get(
    "https://api.oilpriceapi.com/v1/natural-gas/hubs",
    headers={"Authorization": f"Token {os.environ['OILPRICEAPI_KEY']}"},
    timeout=10,
)
resp.raise_for_status()
data = resp.json()["data"]

hh = data["benchmark"]
print(f"Henry Hub: ${hh['price']}/MMBtu\n")
print(f"{'Hub':<28} {'Price':>8} {'Basis':>8}  History")
for hub in data["hubs"]:
    basis = hub.get("basis_to_henry")
    basis_s = f"{basis:+.2f}" if basis is not None else "n/a"
    print(
        f"{hub['name']:<28} {hub['price']:>8} {basis_s:>8}"
        f"  since {hub.get('history_since', '?')}"
    )

# Hub histories differ in depth — check history_days before requesting a
# long window. Single hub with basis history:
#   GET /v1/natural-gas/hubs/waha?past=30d
