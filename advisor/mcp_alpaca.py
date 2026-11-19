"""Conexion al servidor MCP oficial de Alpaca mediante las herramientas MCP de Microsoft Agent Framework.

Restricciones aplicadas (el filtro ALPACA_TOOLSETS del servidor no basta: su grupo "trading"
incluye ventas, cripto, opciones y cierre de posiciones):
1. allowed_tools: lista blanca de 8 herramientas en el cliente.
2. approval_mode: la unica herramienta con efecto (place_stock_order) exige aprobacion humana;
   cualquier herramienta no listada tambien la exigiria (default seguro).
3. verify_alpaca_tool(): comprobacion al arrancar de que lo anterior se aplico de verdad.
"""
from __future__ import annotations

from agent_framework import MCPStdioTool

from advisor.config import (
    ALPACA_ALLOWED_TOOLS, ALPACA_MCP_PACKAGE, ALPACA_ORDER_TOOL, ALPACA_READ_TOOLS, alpaca_env, find_uvx,
)


def build_alpaca_tool() -> MCPStdioTool:
    return MCPStdioTool(
        name="alpaca",
        command=find_uvx(),
        args=[ALPACA_MCP_PACKAGE],
        env=alpaca_env(),
        allowed_tools=ALPACA_ALLOWED_TOOLS,
        approval_mode={
            "always_require_approval": [ALPACA_ORDER_TOOL],
            "never_require_approval": ALPACA_READ_TOOLS,
            "default": "always_require",
        },
        load_prompts=False,
        request_timeout=60,
    )


def verify_alpaca_tool(tool: MCPStdioTool) -> dict[str, str]:
    """Falla al arrancar si la lista blanca o la aprobacion no quedaron como se espera."""
    modes = {f.name: f.approval_mode for f in tool.functions}
    extra = set(modes) - set(ALPACA_ALLOWED_TOOLS)
    missing = set(ALPACA_ALLOWED_TOOLS) - set(modes)
    if extra:
        raise RuntimeError(f"Herramientas MCP fuera de la lista blanca: {sorted(extra)}")
    if missing:
        raise RuntimeError(f"Herramientas MCP esperadas que el servidor no expone: {sorted(missing)}")
    if modes[ALPACA_ORDER_TOOL] != "always_require":
        raise RuntimeError("place_stock_order NO exige aprobacion humana: configuracion insegura.")
    return modes
