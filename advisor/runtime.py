"""Recursos compartidos del proceso (se inicializan al arrancar el servicio)."""
from __future__ import annotations

import json
from typing import Any

kb: Any = None       # kb.search.KnowledgeBase
alpaca: Any = None   # MCPStdioTool conectado


def mcp_text(result: Any) -> str:
    if isinstance(result, str):
        return result
    return "\n".join(getattr(c, "text", None) or str(c) for c in result)


async def alpaca_data(tool_name: str, **kwargs: Any) -> Any:
    """Llama a una herramienta MCP de Alpaca desde codigo (validaciones) y devuelve el campo 'data'."""
    raw = mcp_text(await alpaca.call_tool(tool_name, **kwargs))
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Respuesta no JSON de {tool_name}: {raw[:200]}") from exc
    return parsed.get("data", parsed) if isinstance(parsed, dict) else parsed
