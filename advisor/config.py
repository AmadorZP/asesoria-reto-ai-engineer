"""Configuracion del agente asesor. Todas las credenciales llegan por variables de entorno (.env)."""
from __future__ import annotations

import glob
import os
import shutil
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

ADVISOR_MODEL = os.getenv("ADVISOR_MODEL", "gpt-6-luna")
JUDGE_MODEL = os.getenv("JUDGE_MODEL", "gpt-6.1-terra")
LOG_DIR = ROOT / "logs"

ALPACA_MCP_PACKAGE = os.getenv("ALPACA_MCP_PACKAGE", "alpaca-mcp-server@2.4.1")  # version fijada (anti rug-pull)
ALPACA_TOOLSETS = "account,trading,assets,stock-data,news"

# Lista blanca de herramientas MCP expuestas al agente (minimo privilegio).
ALPACA_READ_TOOLS = [
    "get_clock",            # estado del mercado
    "get_account_info",     # cuenta y poder de compra
    "get_all_positions",    # posiciones actuales
    "get_stock_snapshot",   # precio: ultimo trade, quote, barra diaria y cierre previo
    "get_stock_bars",       # historico para tendencia
    "get_news",             # noticias
    "get_order_by_id",      # estado de una orden
]
ALPACA_ORDER_TOOL = "place_stock_order"  # unica herramienta con efecto; siempre requiere aprobacion humana
ALPACA_ALLOWED_TOOLS = ALPACA_READ_TOOLS + [ALPACA_ORDER_TOOL]


def find_uvx() -> str:
    """Localiza uvx (lanza el servidor MCP de Alpaca en un entorno aislado)."""
    candidates = [os.getenv("UVX_PATH"), shutil.which("uvx")]
    local = os.getenv("LOCALAPPDATA", "")
    if local:
        candidates += glob.glob(os.path.join(local, "Microsoft", "WinGet", "Packages", "astral-sh.uv*", "uvx.exe"))
        candidates.append(os.path.join(local, "Microsoft", "WinGet", "Links", "uvx.exe"))
    for c in candidates:
        if c and os.path.exists(c):
            return c
    raise RuntimeError("No se encontro uvx. Instala uv (winget install astral-sh.uv) o define UVX_PATH en .env.")


def alpaca_env() -> dict[str, str]:
    """El proceso hijo MCP no hereda el entorno: las credenciales se pasan explicitamente."""
    missing = [k for k in ("ALPACA_API_KEY", "ALPACA_SECRET_KEY") if not os.getenv(k)]
    if missing:
        raise RuntimeError(f"Faltan variables de entorno: {missing}")
    return {
        "ALPACA_API_KEY": os.environ["ALPACA_API_KEY"],
        "ALPACA_SECRET_KEY": os.environ["ALPACA_SECRET_KEY"],
        "ALPACA_PAPER_TRADE": "true",   # forzado: este proyecto nunca opera con dinero real
        "ALPACA_TOOLSETS": ALPACA_TOOLSETS,
    }
