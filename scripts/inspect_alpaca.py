"""Muestra los esquemas reales de las herramientas MCP de Alpaca y un ejemplo de salida (solo lectura)."""
from __future__ import annotations

import asyncio
import json

from advisor.mcp_alpaca import build_alpaca_tool


def _text(result) -> str:
    if isinstance(result, str):
        return result
    return "\n".join(getattr(c, "text", None) or str(c) for c in result)


async def main() -> None:
    alpaca = build_alpaca_tool()
    async with alpaca:
        for f in alpaca.functions:
            spec = f.to_json_schema_spec()["function"]
            props = spec["parameters"].get("properties", {})
            print(f"\n### {f.name}  required={spec['parameters'].get('required', [])}")
            for name, p in props.items():
                print(f"   - {name}: {json.dumps({k: v for k, v in p.items() if k in ('type', 'enum', 'default', 'anyOf')})[:140]}")
        for name, kwargs in [("get_clock", {}), ("get_account_info", {}),
                             ("get_stock_snapshot", {"symbols": "MSFT", "feed": "iex"}),
                             ("get_all_positions", {})]:
            try:
                out = _text(await alpaca.call_tool(name, **kwargs))
            except Exception as exc:
                out = f"ERROR: {exc}"
            print(f"\n=== {name}({kwargs}) ===\n{out[:1500]}")


if __name__ == "__main__":
    asyncio.run(main())
