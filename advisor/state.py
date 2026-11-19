"""Estado en memoria del asesor: sesiones (con su perfil inferido), turno en curso y tickets de orden.

Para el reto todo vive en memoria. En produccion: Redis o base de datos para sesiones, y el perfil y
las tenencias vendrian del sistema de registro (CRM / custodia), como ya ocurre aqui con la sesion
especial ligada a la cuenta real de Alpaca.
"""
from __future__ import annotations

import asyncio
import json
import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from advisor.config import LOG_DIR

TOOL_LOG_PATH = LOG_DIR / "tool_calls.jsonl"
ALPACA_SESSION_ID = "cuenta-alpaca"     # sesion especial: capital y tenencias reales de la cuenta paper


@dataclass
class SessionState:
    session_id: str
    kind: str = "inferido"                                    # "inferido" | "alpaca"
    title: str = ""
    created_at: float = field(default_factory=time.time)
    blob: str | None = None                                   # AgentSession serializada (historial + aprobaciones)
    profile: dict | None = None                               # perfil de riesgo registrado en la conversacion
    profile_changes: list[dict] = field(default_factory=list)
    holdings: dict[str, dict] = field(default_factory=dict)   # compras hechas en esta sesion (perfil inferido)
    sources: dict[str, dict] = field(default_factory=dict)    # "S1" -> metadata del fragmento citado
    tickets: dict[str, dict] = field(default_factory=dict)    # ordenes validadas pendientes de aprobacion
    warnings: dict[str, dict] = field(default_factory=dict)   # "MSFT:5" -> {"etapa": 1|2, "turno": n}
    messages: list[dict] = field(default_factory=list)        # transcripcion para la interfaz
    turn_no: int = 0                                          # mensajes del usuario recibidos
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
        event = {"session_id": turn.state.session_id, "turno": turn.state.turn_no, **event}
        turn.trace.append(event)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with TOOL_LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
