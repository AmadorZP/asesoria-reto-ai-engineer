"""Fase 1 del evaluador: ejecuta los casos contra el agente asesor SOLO por su endpoint HTTP.

El evaluador no importa codigo del asesor: es un cliente mas. Juega el papel del humano en la
confirmacion de ordenes segun `approval_policy` de cada caso, y guarda la respuesta cruda con la traza
(fragmentos recuperados y herramientas invocadas) para puntuarla despues, offline.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import requests

TIMEOUT = 400


def load_cases(path: Path, split: str) -> list[dict]:
    cases = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return cases if split == "all" else [c for c in cases if c["split"] == split]


def run_case(base_url: str, case: dict, run_id: str) -> dict:
    session_id = f"eval-{run_id}-{case['id']}"
    responses, error = [], None
    try:
        # Estado limpio por caso (tenencias y sesiones): los casos son independientes entre si.
        requests.post(f"{base_url}/admin/reset", timeout=30).raise_for_status()
        for turn in case["turns"]:
            r = requests.post(f"{base_url}/chat", timeout=TIMEOUT, json={
                "message": turn, "session_id": session_id, "client_id": case["client_id"], "include_trace": True})
            r.raise_for_status()
            resp = r.json()
            responses.append(resp)
            # Humano simulado: solo decide si el caso lo indica; con "none" la orden queda sin confirmar.
            for _ in range(3):
                pending = resp.get("pending_approvals") or []
                if not pending or case["approval_policy"] == "none":
                    break
                r = requests.post(f"{base_url}/approve", timeout=TIMEOUT, json={
                    "session_id": session_id, "approval_id": pending[0]["approval_id"],
                    "approved": case["approval_policy"] == "approve"})
                r.raise_for_status()
                resp = r.json()
                responses.append(resp)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    return {"case": case, "session_id": session_id, "responses": responses, "error": error}


def collect(base_url: str, cases: list[dict], run_id: str, out_path: Path) -> list[dict]:
    records = []
    with out_path.open("w", encoding="utf-8") as fh:
        for i, case in enumerate(cases, start=1):
            started = time.time()
            rec = run_case(base_url, case, run_id)
            rec["wall_ms"] = int((time.time() - started) * 1000)
            records.append(rec)
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()
            print(f"  [{i:2d}/{len(cases)}] {case['id']:4s} {case['category']:17s} {rec['wall_ms'] / 1000:5.1f}s"
                  + (f"  ERROR {rec['error']}" if rec["error"] else ""))
    return records


def cancel_paper_orders(records: list[dict]) -> list[dict]:
    """Limpieza: cancela en Alpaca (paper) las ordenes que coloco esta corrida, para que no se ejecuten
    en la proxima apertura ni consuman poder de compra. La hace el evaluador, no el agente."""
    key, secret = os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_SECRET_KEY")
    out = []
    order_ids = {o["order_id"] for rec in records for resp in rec["responses"] for o in resp.get("orders", []) if o.get("order_id")}
    for oid in sorted(order_ids):
        try:
            r = requests.delete(f"https://paper-api.alpaca.markets/v2/orders/{oid}", timeout=30,
                                headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret})
            out.append({"order_id": oid, "http_status": r.status_code,
                        "resultado": "cancelada" if r.status_code == 204 else "no cancelable (ya ejecutada o cerrada)"})
        except Exception as exc:
            out.append({"order_id": oid, "resultado": f"error: {exc}"})
    return out
