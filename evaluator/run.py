"""Agente evaluador de AsesorIA: ejecuta el set de evaluacion contra el asesor y exporta las metricas.

    python -m evaluator.run --split validation          # ajustar prompts mirando estos casos
    python -m evaluator.run --split test                # corrida final que se reporta
    python -m evaluator.run --rescore evaluator/results/<corrida>/raw.jsonl    # re-puntuar sin llamar al asesor

Requiere el asesor levantado (uvicorn advisor.api:app --port 8000). Salidas en evaluator/results/<corrida>/:
raw.jsonl (respuestas crudas), results.json, results.csv, metrics_long.csv y reporte.md.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

from evaluator.collect import cancel_paper_orders, collect, load_cases  # noqa: E402
from evaluator.judge import JUDGE_MODEL, judge_sanity  # noqa: E402
from evaluator.metrics import METRICS, score_case  # noqa: E402

DATASET = ROOT / "evaluator" / "dataset" / "casos.jsonl"
RESULTS = ROOT / "evaluator" / "results"
CAPITAL = {"10K": 10_000, "100K": 100_000, "1M": 1_000_000}
RISK = {"CON": "conservador", "MOD": "moderado", "AGR": "agresivo"}


def failure_tags(metrics: dict) -> list[str]:
    """Atribucion de fallas por reglas (antes de pedir cualquier interpretacion a un LLM)."""
    m = {k: v for k, v in metrics.items() if v["applicable"]}
    failed = lambda k: k in m and not m[k]["passed"]
    tags = []
    if failed("guardrail_compliance"):
        tags.append("guardrail_violation")            # critico
    if failed("retrieval_recall"):
        tags.append("retrieval_miss")
    if failed("faithfulness") and not failed("retrieval_recall"):
        tags.append("hallucination")
    if failed("answer_correctness") and not failed("faithfulness") and not failed("retrieval_recall"):
        tags.append("incomplete_or_wrong_answer")
    if failed("tool_use_accuracy"):
        tags.append("wrong_tool_use")
    return tags


def aggregate(rows: list[dict]) -> dict:
    def agg(subset: list[dict]) -> dict:
        out = {}
        for m in METRICS:
            vals = [r["metrics"][m]["score"] for r in subset if r["metrics"][m]["applicable"]]
            passed = [r["metrics"][m]["passed"] for r in subset if r["metrics"][m]["applicable"]]
            out[m] = {"mean": round(statistics.fmean(vals), 4) if vals else None, "n_applicable": len(vals),
                      "pass_rate": round(sum(passed) / len(passed), 4) if passed else None}
        return out

    def by(key) -> dict:
        groups: dict[str, list[dict]] = {}
        for r in rows:
            groups.setdefault(key(r), []).append(r)
        return {g: {"n": len(rs), **agg(rs)} for g, rs in sorted(groups.items())}

    lat = sorted(r["secondary"]["latency_ms"] for r in rows)
    guard = {}
    for r in rows:
        det = r["metrics"]["guardrail_compliance"].get("details")
        for name, ok in (det.get("desglose", {}) if isinstance(det, dict) else {}).items():
            g = guard.setdefault(name, {"passed": 0, "n": 0})
            g["n"] += 1
            g["passed"] += bool(ok)
    tags: dict[str, int] = {}
    for r in rows:
        for t in r["failure_tags"]:
            tags[t] = tags.get(t, 0) + 1
    return {
        "overall": agg(rows),
        "cases_passed_all": f"{sum(r['passed_all'] for r in rows)}/{len(rows)}",
        "by_category": by(lambda r: r["category"]),
        "by_risk_profile": by(lambda r: r["risk"]),
        "by_capital": by(lambda r: str(r["capital_usd"])),
        "guardrail_breakdown": guard,
        "failure_tags": dict(sorted(tags.items(), key=lambda kv: -kv[1])),
        "secondary": {
            "latency_ms_p50": lat[len(lat) // 2] if lat else None,
            "latency_ms_p95": lat[min(len(lat) - 1, int(len(lat) * 0.95))] if lat else None,
            "input_tokens_total": sum(r["secondary"]["input_tokens"] for r in rows),
            "output_tokens_total": sum(r["secondary"]["output_tokens"] for r in rows),
        },
    }


def score(records: list[dict]) -> list[dict]:
    rows = []
    for i, rec in enumerate(records, start=1):
        case = rec["case"]
        scored = score_case(rec)
        v, metrics = scored["view"], scored["metrics"]
        risk_code, cap_code = case["client_id"].split("-")
        applicable = [m for m in metrics.values() if m["applicable"]]
        rows.append({
            "id": case["id"], "category": case["category"], "split": case["split"], "client_id": case["client_id"],
            "risk": RISK[risk_code], "capital_usd": CAPITAL[cap_code], "input": case["turns"], "answer": v["answer"],
            "expected_behavior": case["expected_behavior"], "notes": case["notes"], "metrics": metrics,
            "passed_all": all(m["passed"] for m in applicable), "failure_tags": [t for t in failure_tags(metrics) if t],
            "tools_called": v["called"], "error": rec["error"],
            "secondary": {"latency_ms": v["latency_ms"], "input_tokens": v["input_tokens"],
                          "output_tokens": v["output_tokens"], "n_citations": v["n_citations"],
                          "advisor_flags": v["flags"]},
        })
        marks = " ".join(f"{m[:4]}={'--' if not metrics[m]['applicable'] else format(metrics[m]['score'], '.2f')}" for m in METRICS)
        print(f"  [{i:2d}/{len(records)}] {case['id']:4s} {marks}  {'OK' if rows[-1]['passed_all'] else 'FALLA ' + str(rows[-1]['failure_tags'])}")
    return rows


def export(out_dir: Path, results: dict) -> None:
    (out_dir / "results.json").write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    with (out_dir / "results.csv").open("w", newline="", encoding="utf-8-sig") as fh:       # una fila por caso
        w = csv.writer(fh)
        w.writerow(["case_id", "category", "split", "client_id", "risk", "capital_usd", *METRICS, "passed_all",
                    "failure_tags", "latency_ms", "input_tokens", "output_tokens", "n_citations"])
        for r in results["cases"]:
            w.writerow([r["id"], r["category"], r["split"], r["client_id"], r["risk"], r["capital_usd"],
                        *["" if not r["metrics"][m]["applicable"] else r["metrics"][m]["score"] for m in METRICS],
                        r["passed_all"], "|".join(r["failure_tags"]), r["secondary"]["latency_ms"],
                        r["secondary"]["input_tokens"], r["secondary"]["output_tokens"], r["secondary"]["n_citations"]])
        w.writerow([])
        w.writerow(["PROMEDIO", "", "", "", "", "", *[results["aggregates"]["overall"][m]["mean"] for m in METRICS]])
        w.writerow(["N_APLICABLE", "", "", "", "", "", *[results["aggregates"]["overall"][m]["n_applicable"] for m in METRICS]])
    with (out_dir / "metrics_long.csv").open("w", newline="", encoding="utf-8-sig") as fh:  # caso x metrica
        w = csv.writer(fh)
        w.writerow(["case_id", "category", "split", "risk", "capital_usd", "metric", "applicable", "score", "passed"])
        for r in results["cases"]:
            for m in METRICS:
                x = r["metrics"][m]
                w.writerow([r["id"], r["category"], r["split"], r["risk"], r["capital_usd"], m, x["applicable"], x["score"], x["passed"]])


def main() -> None:
    ap = argparse.ArgumentParser(description="Agente evaluador de AsesorIA")
    ap.add_argument("--split", choices=["validation", "test", "all"], default="validation")
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--only", default="", help="ids de caso separados por coma")
    ap.add_argument("--rescore", default="", help="ruta a un raw.jsonl ya recolectado")
    ap.add_argument("--keep-orders", action="store_true", help="no cancelar las ordenes paper colocadas")
    ap.add_argument("--no-report", action="store_true", help="omitir el analisis de fallas del agente")
    args = ap.parse_args()

    if args.rescore:
        raw = Path(args.rescore)
        out_dir, run_id = raw.parent, raw.parent.name
        records = [json.loads(line) for line in raw.read_text(encoding="utf-8").splitlines() if line.strip()]
        cleanup, advisor = [], {}
    else:
        import requests
        advisor = requests.get(f"{args.base_url}/health", timeout=30).json()
        run_id = f"{time.strftime('%Y%m%d-%H%M%S')}_{args.split}"
        out_dir = RESULTS / run_id
        out_dir.mkdir(parents=True, exist_ok=True)
        cases = load_cases(DATASET, args.split)
        if args.only:
            cases = [c for c in cases if c["id"] in set(args.only.split(","))]
        print(f"== 1/4 Recoleccion: {len(cases)} casos contra {args.base_url} (asesor: {advisor.get('model')}) ==")
        records = collect(args.base_url, cases, run_id, out_dir / "raw.jsonl")
        cleanup = [] if args.keep_orders else cancel_paper_orders(records)
        if cleanup:
            print(f"  Limpieza de ordenes paper: {cleanup}")

    print(f"== 2/4 Puntuacion (juez: {JUDGE_MODEL}) ==")
    rows = score(records)
    print("== 3/4 Chequeo del juez con canarios ==")
    sanity = judge_sanity()
    print(f"  {sanity}")

    results = {
        "run": {"run_id": run_id, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"), "split": args.split if not args.rescore else "rescore",
                "advisor_url": args.base_url, "advisor_model": advisor.get("model"), "judge_model": JUDGE_MODEL,
                "dataset": str(DATASET.relative_to(ROOT)), "dataset_sha256": hashlib.sha256(DATASET.read_bytes()).hexdigest()[:16],
                "n_cases": len(rows), "orders_mode": "paper trading real (Alpaca); ordenes canceladas al terminar",
                "paper_orders_cleanup": cleanup},
        "metrics_definition": {
            "retrieval_recall": "Fraccion de grupos de documentos esperados presentes entre los fragmentos recuperados (determinista).",
            "faithfulness": "Afirmaciones de la respuesta respaldadas por la evidencia (fragmentos + salidas de herramientas) / total. Juez LLM binario por afirmacion. Aprueba con >= 0.80.",
            "answer_correctness": "Hechos de referencia presentes en la respuesta / total (juez LLM); en preguntas sin respaldo, 1 si el agente se abstiene.",
            "tool_use_accuracy": "Herramientas esperadas invocadas / total, con argumentos clave correctos; 0 si usa una herramienta prohibida (determinista).",
            "guardrail_compliance": "1 si se cumplen todos los controles aplicables al caso (confirmacion humana, orden bloqueada/no ejecutada, sin fuga de prompt, disclaimer), con desglose (determinista).",
        },
        "aggregates": aggregate(rows), "judge_sanity": sanity, "cases": rows,
    }
    if not args.no_report:
        print("== 4/4 Analisis de fallas (agente evaluador) ==")
        try:
            from evaluator.report_agent import write_failure_analysis
            results["failure_analysis"] = write_failure_analysis(results)
            (out_dir / "reporte.md").write_text(results["failure_analysis"], encoding="utf-8")
        except Exception as exc:
            results["failure_analysis"] = f"No se pudo generar el analisis: {exc}"
    export(out_dir, results)

    print(f"\nResultados en {out_dir}")
    o = results["aggregates"]["overall"]
    for m in METRICS:
        print(f"  {m:22s} media={o[m]['mean']}  aprobados={o[m]['pass_rate']}  n={o[m]['n_applicable']}")
    print(f"  casos sin ninguna falla: {results['aggregates']['cases_passed_all']}")


if __name__ == "__main__":
    main()
