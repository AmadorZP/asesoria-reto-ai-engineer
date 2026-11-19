"""Orquestacion de un turno: sesion, ejecucion del agente, human-in-the-loop, citas y guardrails de salida."""
from __future__ import annotations

import json
import re
import time

from agent_framework import AgentSession, Content, Message

from advisor import runtime
from advisor.agent import build_agent
from advisor.config import ADVISOR_MODEL, ALPACA_ORDER_TOOL
from advisor.mcp_alpaca import build_alpaca_tool, verify_alpaca_tool
from advisor.middleware import find_ticket
from advisor.profile import financials, has_profile, profile_view
from advisor.prompts import ABSTENCION, CANARY, DISCLAIMER
from advisor.state import ALPACA_SESSION_ID, TURN, SessionState, Turn, log_event

INJECTION_INPUT = re.compile(
    r"(ignora (todas )?(las|tus) (instrucciones|reglas)|olvida (todas )?(las|tus) (instrucciones|reglas)|"
    r"ignore (all |any )?(previous|prior|your) (instructions|rules)|system prompt|prompt (del|de) sistema|"
    r"modo desarrollador|developer mode|jailbreak|sin (pedir )?confirmaci[oó]n|without confirmation|"
    r"sin (m[aá]s )?advertencias|actualizaci[oó]n del sistema|"
    r"act[uú]a como|eres ahora|you are now|revela (tus|las) instrucciones|reveal your (prompt|instructions))",
    re.IGNORECASE)
CITATION = re.compile(r"\[(S\d+)\]")
MAX_MESSAGE_CHARS = 4000


class SessionError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status, self.detail = status, detail


class AdvisorService:
    def __init__(self) -> None:
        self.sessions: dict[str, SessionState] = {}
        self.agent = None
        self.mcp_tools: dict[str, str] = {}

    # ------------------------------------------------------------------ ciclo de vida
    async def start(self) -> None:
        from kb.search import KnowledgeBase

        runtime.kb = KnowledgeBase()
        runtime.alpaca = build_alpaca_tool()
        await runtime.alpaca.connect()
        self.mcp_tools = verify_alpaca_tool(runtime.alpaca)   # falla si la lista blanca o la aprobacion no aplican
        self.agent = build_agent(runtime.alpaca)

    async def stop(self) -> None:
        if runtime.alpaca is not None:
            await runtime.alpaca.close()
        if runtime.kb is not None:
            runtime.kb.close()

    def reset(self) -> None:
        self.sessions.clear()

    # ------------------------------------------------------------------ sesiones
    def _state(self, session_id: str) -> SessionState:
        state = self.sessions.get(session_id)
        if state is None:
            kind = "alpaca" if session_id == ALPACA_SESSION_ID else "inferido"
            state = self.sessions[session_id] = SessionState(session_id=session_id, kind=kind)
        return state

    def _load(self, state: SessionState) -> AgentSession:
        if state.blob:
            return AgentSession.from_dict(json.loads(state.blob))
        return self.agent.create_session(session_id=state.session_id)

    @staticmethod
    def _pending(session: AgentSession) -> list[Content]:
        raw = session.state.get("tool_approval", {}).get("pending_approval_requests", [])
        return [Content.from_dict(p) for p in raw]

    async def _summary(self, state: SessionState) -> dict:
        fin = await financials(state) if (state.kind == "alpaca" or has_profile(state)) else \
            {"capital_total": (state.profile or {}).get("capital_invertible_usd"), "capital_disponible": None,
             "tenencias": state.holdings, "fuente": "declarado por el cliente en la conversacion"}
        return {"session_id": state.session_id, "kind": state.kind, "title": state.title or "Nueva conversación",
                "created_at": state.created_at, "n_messages": len(state.messages),
                "profile": profile_view(state, fin), "profile_changes": state.profile_changes}

    async def list_sessions(self) -> list[dict]:
        self._state(ALPACA_SESSION_ID)   # la sesion especial siempre existe
        ordered = sorted(self.sessions.values(), key=lambda s: (s.kind != "alpaca", -s.created_at))
        return [await self._summary(s) for s in ordered]

    async def get_session(self, session_id: str) -> dict:
        if session_id not in self.sessions and session_id != ALPACA_SESSION_ID:
            raise SessionError(404, "Sesion desconocida.")
        state = self._state(session_id)
        return {**await self._summary(state), "messages": state.messages}

    # ------------------------------------------------------------------ turnos
    async def chat(self, session_id: str, message: str) -> dict:
        message = (message or "").strip()
        if not message:
            raise SessionError(400, "El mensaje esta vacio.")
        if len(message) > MAX_MESSAGE_CHARS:
            raise SessionError(413, f"El mensaje supera {MAX_MESSAGE_CHARS} caracteres.")
        state = self._state(session_id)
        async with state.lock:
            state.turn_no += 1
            state.title = state.title or message[:60]
            turn, started = Turn(state), time.time()
            token = TURN.set(turn)
            session = self._load(state)
            try:
                # Un mensaje nuevo NO es una confirmacion: cualquier orden pendiente se rechaza.
                pending = self._pending(session)
                if pending:
                    log_event(turn, {"event": "approval_decision", "approved": False, "by": "system",
                                     "reason": "llego un mensaje nuevo sin confirmar la orden pendiente"})
                    await self.agent.run(
                        Message("user", [p.to_function_approval_response(False) for p in pending]), session=session)
                if INJECTION_INPUT.search(message):
                    turn.flags.append("posible_prompt_injection")
                log_event(turn, {"event": "user_message", "text": message, "flags": list(turn.flags)})
                state.messages.append({"role": "user", "text": message})
                result = await self.agent.run(message, session=session)
                result = await self._reject_invalid_orders(result, session, turn)
                return await self._render(result, turn, started)
            finally:
                state.blob = json.dumps(session.to_dict())
                TURN.reset(token)

    async def approve(self, session_id: str, approval_id: str, approved: bool) -> dict:
        state = self.sessions.get(session_id)
        if state is None:
            raise SessionError(404, "Sesion desconocida.")
        async with state.lock:
            turn, started = Turn(state), time.time()
            token = TURN.set(turn)
            session = self._load(state)
            try:
                pending = {c.id: c for c in self._pending(session)}
                if approval_id not in pending:
                    raise SessionError(409, "No existe una aprobacion pendiente con ese id (ya resuelta o inexistente).")
                req = pending[approval_id]
                log_event(turn, {"event": "approval_decision", "approved": approved, "by": "human",
                                 "tool": req.function_call.name, "args": req.function_call.parse_arguments()})
                state.messages.append({"role": "decision", "approved": approved})
                result = await self.agent.run(
                    Message("user", [req.to_function_approval_response(approved)]), session=session)
                result = await self._reject_invalid_orders(result, session, turn)
                return await self._render(result, turn, started)
            finally:
                state.blob = json.dumps(session.to_dict())
                TURN.reset(token)

    async def _reject_invalid_orders(self, result, session: AgentSession, turn: Turn):
        """Si el modelo intenta una orden sin validacion vigente, se rechaza antes de molestar al humano."""
        for _ in range(3):
            reqs = [r for r in result.user_input_requests if r.type == "function_approval_request"]
            invalid = []
            for r in reqs:
                args = r.function_call.parse_arguments() or {}
                motivo = "herramienta no autorizada" if r.function_call.name != ALPACA_ORDER_TOOL \
                    else find_ticket(turn.state.tickets, args)[1]
                if motivo:
                    invalid.append((r, args, motivo))
            if not invalid:
                return result
            for r, args, motivo in invalid:
                log_event(turn, {"event": "approval_decision", "approved": False, "by": "system",
                                 "tool": r.function_call.name, "args": args, "reason": motivo})
            result = await self.agent.run(
                Message("user", [r.to_function_approval_response(False) for r in reqs]), session=session)
        return result

    # ------------------------------------------------------------------ salida
    async def _render(self, result, turn: Turn, started: float) -> dict:
        state = turn.state
        answer = (result.text or "").strip()

        pending = []
        for r in result.user_input_requests:
            if r.type != "function_approval_request":
                continue
            args = r.function_call.parse_arguments() or {}
            ticket, _ = find_ticket(state.tickets, args)
            # La tarjeta de confirmacion se arma con los argumentos REALES de la llamada y con el ticket
            # validado por codigo, nunca con texto redactado por el modelo.
            pending.append({
                "approval_id": r.id, "tool": r.function_call.name, "arguments": args,
                "resumen": {"operacion": "COMPRA", "simbolo": ticket["symbol"], "cantidad": ticket["qty"],
                            "precio_referencia_usd": ticket["price"], "monto_estimado_usd": ticket["monto"],
                            "tipo": "market", "vigencia": "day"} if ticket else None,
                "validaciones": ticket["validaciones"] if ticket else [],
                "advertencias": ticket["advertencias"] if ticket else [],
                "perfil_modificado_tras_advertencia": any(c.get("tras_advertencia") for c in state.profile_changes),
                "mercado": ticket["mercado"] if ticket else None,
            })
            log_event(turn, {"event": "approval_requested", "approval_id": r.id,
                             "tool": r.function_call.name, "args": args})
        if pending and not answer:
            p, adv = pending[0]["resumen"], pending[0]["advertencias"]
            if p:
                answer = (f"Orden lista para tu confirmación: COMPRA de {p['cantidad']} {p['simbolo']} a mercado, precio de "
                          f"referencia USD {p['precio_referencia_usd']:,.2f}, monto estimado USD {p['monto_estimado_usd']:,.2f} "
                          f"(paper trading). "
                          + ("Excede los límites recomendados para tu perfil; ya te lo advertí y decidiste continuar. "
                             if adv else "Cumple los límites recomendados para tu perfil. ")
                          + "¿Confirmas la ejecución?")
            else:
                answer = "Hay una acción pendiente de tu confirmación."

        # Guardrail de salida 1: fuga del prompt (canario).
        if CANARY in answer:
            turn.flags.append("fuga_de_prompt_bloqueada")
            answer = "No puedo compartir esa información. ¿En qué consulta de inversión te ayudo?"

        # Guardrail de salida 2: citas verificadas. Solo sobreviven los [S#] que existen en la sesion.
        cited: list[str] = []

        def _check(m: re.Match) -> str:
            sid = m.group(1)
            if sid in state.sources:
                if sid not in cited:
                    cited.append(sid)
                return m.group(0)
            turn.flags.append(f"cita_invalida_eliminada:{sid}")
            return ""
        answer = CITATION.sub(_check, answer)
        citations = [{
            "sid": sid, "titulo": s["doc_title"], "seccion": f"{s['section']} {s.get('section_title') or ''}".strip(),
            "pagina": s.get("page_start"), "url": s["source_url"], "doc_type": s["doc_type"],
            "simulado": bool(s.get("is_simulated")), "extracto": (s.get("text") or "")[:400],
        } for sid, s in ((c, state.sources[c]) for c in cited)]

        # Guardrail de salida 3: abstencion. Si se consulto la base, no devolvio nada y no hubo otra fuente
        # de datos, la respuesta debe declarar que no hay informacion suficiente.
        if turn.kb_calls and not turn.kb_hits and not turn.data_calls and ABSTENCION.lower() not in answer.lower():
            turn.flags.append("abstencion_forzada")
            answer = f"{ABSTENCION} en la base de conocimiento para responder esta consulta.\n\n{answer}".strip()

        orders = [{"ticket_id": t["ticket_id"], "order_id": t.get("order_id"), "status": t.get("status"),
                   "simbolo": t["symbol"], "cantidad": t["qty"],
                   "excepcion_de_politica": [a["regla"] for a in t.get("advertencias", [])]}
                  for t in state.tickets.values() if t["estado"] == "ejecutado"]
        usage = getattr(result, "usage_details", None)
        summary = await self._summary(state)
        response = {
            "session_id": state.session_id, "session_kind": state.kind, "title": summary["title"],
            "answer": answer, "citations": citations, "pending_approvals": pending, "orders": orders,
            "profile": summary["profile"], "profile_changes": state.profile_changes,
            "flags": turn.flags, "trace": turn.trace, "retrieved": turn.retrieved, "disclaimer": DISCLAIMER,
            "abstained": ABSTENCION.lower() in answer.lower(),
            "usage": dict(usage) if usage else None, "model": ADVISOR_MODEL,
            "latency_ms": int((time.time() - started) * 1000),
        }
        state.messages.append({"role": "assistant", "response": {k: v for k, v in response.items() if k != "retrieved"}})
        return response
