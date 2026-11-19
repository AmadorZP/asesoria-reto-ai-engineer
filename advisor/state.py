"""Estado en memoria del asesor: sesiones, turno en curso, tickets de orden y libro de tenencias.

Para el reto todo vive en memoria/archivos locales. En produccion: Redis o base de datos
para sesiones y un sistema de registro (OMS/core) para tenencias.
"""
from __future__ import annotations

import asyncio
import json
import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from advisor.config import LOG_DIR

LEDGER_PATH = LOG_DIR / "ledger.json"
TOOL_LOG_PATH = LOG_DIR / "tool_calls.jsonl"


@dataclass
class SessionState:
    session_id: str
    client_id: str
    blob: str | None = None                                   # AgentSession serializada (historial + aprobaciones pendientes)
    sources: dict[str, dict] = field(default_factory=dict)    # "S1" -> metadata del fragmento citado
    tickets: dict[str, dict] = field(default_factory=dict)    # ordenes validadas pendientes de aprobacion
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


@dataclass
class Turn:
    """Datos del turno en curso; las tools y el middleware lo leen via contextvar."""
    state: SessionState
    trace: list[dict] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    retrieved: list[dict] = field(default_factory=list)   # fragmentos recuperados en este turno (para evaluacion)
    kb_calls: int = 0
    kb_hits: int = 0
    data_calls: int = 0     # llamadas a herramientas de datos (MCP, perfil, calculadora)


TURN: ContextVar[Turn | None] = ContextVar("asesoria_turn", default=None)


def current_turn() -> Turn:
    turn = TURN.get()
    if turn is None:
        raise RuntimeError("No hay un turno activo (la tool se invoco fuera de una sesion).")
    return turn


def log_event(turn: Turn | None, event: dict[str, Any]) -> None:
    """Traza de cada decision: se devuelve en la respuesta y se persiste en logs/tool_calls.jsonl."""
    event = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), **event}
    if turn is not None:
        event = {"session_id": turn.state.session_id, "client_id": turn.state.client_id, **event}
        turn.trace.append(event)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with TOOL_LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")


class Ledger:
    """Tenencias por cliente (una sola cuenta paper no puede representar a 9 clientes)."""

    def __init__(self) -> None:
        self.data: dict[str, dict[str, dict]] = {}
        if LEDGER_PATH.exists():
            self.data = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))

    def holdings(self, client_id: str) -> dict[str, dict]:
        return self.data.get(client_id, {})

    def add(self, client_id: str, symbol: str, qty: float, monto: float) -> None:
        pos = self.data.setdefault(client_id, {}).setdefault(symbol, {"cantidad": 0, "monto_usd": 0.0})
        pos["cantidad"] += qty
        pos["monto_usd"] = round(pos["monto_usd"] + monto, 2)
        self._save()

    def reset(self) -> None:
        self.data = {}
        self._save()

    def _save(self) -> None:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        LEDGER_PATH.write_text(json.dumps(self.data, indent=2), encoding="utf-8")


LEDGER = Ledger()
