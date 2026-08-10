"""Give an AI agent live commodity prices — tool function + MCP.

A commodity-price tool for an LLM agent is one plain function. The
adapters below expose it to OpenAI tool-calling and LangChain; the MCP
config at the bottom skips the custom code entirely.

Agent guardrails that matter in practice:
- Never let the model invent a commodity code — resolve names against
  GET /v1/commodities and fail closed on unknowns.
- Always surface `created_at`/`as_of` to the user; a price without its
  timestamp invites the model to present stale data as current.

    OILPRICEAPI_KEY=... python 09_agent_tool.py brent

Requires a free key or higher.
"""

import os
import sys

import requests

KEY = os.environ.get("OILPRICEAPI_KEY")
if not KEY:
    raise SystemExit("Set OILPRICEAPI_KEY — free key at https://oilpriceapi.com/auth/signup")


def get_commodity_price(code: str) -> dict:
    """The whole tool. Returns {code, price, currency, unit, as_of}."""
    resp = requests.get(
        "https://api.oilpriceapi.com/v1/prices/latest",
        headers={"Authorization": f"Token {KEY}"},
        params={"by_code": code},
        timeout=10,
    )
    resp.raise_for_status()
    d = resp.json()["data"]
    return {k: d[k] for k in ("code", "price", "currency", "unit") } | {"as_of": d["created_at"]}


# --- OpenAI tool-calling schema for the same function -----------------
OPENAI_TOOL = {
    "type": "function",
    "function": {
        "name": "get_commodity_price",
        "description": "Latest price for an energy commodity by OilPriceAPI code, e.g. BRENT_CRUDE_USD, WTI_USD, NATURAL_GAS_USD.",
        "parameters": {
            "type": "object",
            "properties": {"code": {"type": "string"}},
            "required": ["code"],
        },
    },
}

# --- LangChain adapter (uncomment if langchain installed) -------------
# from langchain_core.tools import tool
# get_price_tool = tool(get_commodity_price)

if __name__ == "__main__":
    print(get_commodity_price(sys.argv[1].upper() if len(sys.argv) > 1 else "BRENT_CRUDE_USD"))

# --- No-code alternative: MCP ----------------------------------------
# Claude Desktop / Cursor / any MCP client gets 36 tools over the same
# data — including as_of vintage history and per-tool plan requirements
# in the schemas — with this config and no custom code:
#
#   { "mcpServers": { "oilpriceapi": {
#       "command": "npx", "args": ["-y", "oilpriceapi-mcp"],
#       "env": { "OILPRICEAPI_KEY": "your-key" } } } }
#
# Prefer MCP when the agent should DISCOVER capabilities; prefer a
# bespoke tool when you want a locked-down surface.
