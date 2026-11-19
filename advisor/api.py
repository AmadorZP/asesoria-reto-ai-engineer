"""Endpoint HTTP del agente asesor.

    uvicorn advisor.api:app --port 8000

POST /chat             conversa con el agente (respuesta, citas, perfil, traza y aprobaciones pendientes)
POST /approve          confirma o rechaza una orden pendiente (human-in-the-loop)
GET  /sessions         conversaciones con su perfil inferido (la primera es la cuenta real de Alpaca)
GET  /sessions/{id}    transcripcion y perfil de una conversacion
GET  /health           estado, modelo y herramientas MCP expuestas
POST /admin/reset      (solo desarrollo/evaluacion) limpia las sesiones
"""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from advisor import runtime
from advisor.config import ADVISOR_MODEL
from advisor.service import AdvisorService, SessionError
from advisor.state import ALPACA_SESSION_ID

STATIC = Path(__file__).parent / "static"
service = AdvisorService()


@asynccontextmanager
async def lifespan(_: FastAPI):
    await service.start()
    yield
    await service.stop()


app = FastAPI(title="AsesorIA - Agente asesor", version="2.0", lifespan=lifespan)


class ChatIn(BaseModel):
    message: str = Field(..., description="Mensaje del usuario")
    session_id: str | None = Field(None, description=(
        f"Id de la conversacion; si se omite se crea una nueva. '{ALPACA_SESSION_ID}' es la sesion ligada a la "
        "cuenta real de Alpaca (capital y tenencias reales)."))
    include_trace: bool = Field(True, description="Incluir la traza de herramientas en la respuesta")


class ApproveIn(BaseModel):
    session_id: str
    approval_id: str
    approved: bool


def _out(result: dict, include_trace: bool = True) -> dict:
    if not include_trace:
        result = {k: v for k, v in result.items() if k not in ("trace", "retrieved")}
    return result


@app.post("/chat")
async def chat(body: ChatIn) -> dict:
    session_id = body.session_id or f"s-{uuid.uuid4().hex[:12]}"
    try:
        return _out(await service.chat(session_id, body.message), body.include_trace)
    except SessionError as exc:
        raise HTTPException(exc.status, exc.detail) from exc


@app.post("/approve")
async def approve(body: ApproveIn) -> dict:
    try:
        return _out(await service.approve(body.session_id, body.approval_id, body.approved))
    except SessionError as exc:
        raise HTTPException(exc.status, exc.detail) from exc


@app.get("/sessions")
async def sessions() -> list[dict]:
    return await service.list_sessions()


@app.get("/sessions/{session_id}")
async def session_detail(session_id: str) -> dict:
    try:
        return await service.get_session(session_id)
    except SessionError as exc:
        raise HTTPException(exc.status, exc.detail) from exc


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "model": ADVISOR_MODEL, "mcp_tools": service.mcp_tools,
            "knowledge_base": runtime.kb.coverage() if runtime.kb else None, "sessions": len(service.sessions)}


@app.post("/admin/reset")
async def admin_reset() -> dict:
    service.reset()
    return {"status": "reset"}


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")
