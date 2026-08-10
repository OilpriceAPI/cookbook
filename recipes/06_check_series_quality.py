"""Check a series' quality grade before you depend on it.

Every series carries a computed quality report — overall grade plus
dimension scores (completeness, freshness) for the current period,
derived from measured data. Ask the API how reliable a series is before
building on it.

    OILPRICEAPI_KEY=... python 06_check_series_quality.py BRENT_CRUDE_USD

Catalogue summary works on any key; per-series reports need a paid key.
"""

import os
import sys

import requests

code = sys.argv[1] if len(sys.argv) > 1 else "BRENT_CRUDE_USD"

resp = requests.get(
    f"https://api.oilpriceapi.com/v1/data-quality/reports/{code}",
    headers={"Authorization": f"Token {os.environ['OILPRICEAPI_KEY']}"},
    timeout=10,
)
resp.raise_for_status()
report = resp.json()["data"]["report"]

print(f"{report['code']} — {report['name']}")
print(f"grade: {report['grade']}  score: {report['overall_score']}")
for dim, detail in report.get("dimensions", {}).items():
    print(f"  {dim:<14} {detail['score']:<3} ({detail['value']})")

# Catalogue-wide grade distribution (any key):
#   GET /v1/data-quality/summary
