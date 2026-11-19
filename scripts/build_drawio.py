"""Genera docs/diagramas.drawio: los diagramas del proyecto en formato nativo de draw.io (editables).

    python -m scripts.build_drawio

Paginas: 1) Arquitectura  2) Flujo de un mensaje  3) Flujo de compra  4) Controles de salida.
Abrir con https://app.diagrams.net (Archivo > Abrir desde > Dispositivo) o con draw.io Desktop.
"""
from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import quoteattr

OUT = Path(__file__).resolve().parent.parent / "docs" / "diagramas.drawio"

BASE = "whiteSpace=wrap;html=1;fontSize=12;"
STYLES = {
    "proc": "rounded=1;" + BASE + "fillColor=#dae8fc;strokeColor=#6c8ebf;",
    "code": "rhombus;" + BASE + "fillColor=#ffe6cc;strokeColor=#d79b00;strokeWidth=3;",       # decide el codigo
    "model": "rhombus;" + BASE + "fillColor=#e1d5e7;strokeColor=#9673a6;",                    # decide el modelo
    "human": "rhombus;" + BASE + "fillColor=#d5e8d4;strokeColor=#82b366;strokeWidth=2;",      # decide el humano
    "term": "ellipse;" + BASE + "fillColor=#f5f5f5;strokeColor=#666666;fontStyle=1;",
    "stop": "rounded=1;" + BASE + "fillColor=#f8cecc;strokeColor=#b85450;",
    "ok": "rounded=1;" + BASE + "fillColor=#d5e8d4;strokeColor=#82b366;",
    "warn": "rounded=1;" + BASE + "fillColor=#fff2cc;strokeColor=#d6b656;",
    "ext": "rounded=1;dashed=1;" + BASE + "fillColor=#fff2cc;strokeColor=#d6b656;",
    "db": "shape=cylinder3;boundedLbl=1;backgroundOutline=1;size=12;" + BASE + "fillColor=#e1d5e7;strokeColor=#9673a6;",
    "agent": "rounded=1;" + BASE + "fillColor=#1b4f8a;strokeColor=#0b2f5a;fontColor=#ffffff;fontStyle=1;",
    "note": "shape=note;size=14;" + BASE + "fillColor=#ffffff;strokeColor=#999999;align=left;spacingLeft=8;fontSize=11;",
    "title": "text;html=1;align=left;verticalAlign=middle;fontSize=18;fontStyle=1;",
}
SIZES = {"code": (210, 110), "model": (210, 110), "human": (210, 110), "term": (190, 60), "db": (170, 80),
         "note": (300, 110), "title": (700, 30)}
EDGE = "edgeStyle=orthogonalEdgeStyle;rounded=1;orthogonalLoop=1;jettySize=auto;html=1;fontSize=11;endArrow=block;endFill=1;"
LEGEND = ("<b>Leyenda</b><br>Rombo naranja (borde grueso): decide el <b>c&oacute;digo</b><br>"
          "Rombo morado: decide el <b>modelo</b><br>Rombo verde: decide el <b>humano</b><br>"
          "Rojo: bloqueo o rechazo &middot; Amarillo: advertencia")


class Page:
    def __init__(self, name: str, col: int = 250, row: int = 140, x0: int = 40, y0: int = 80) -> None:
        self.name, self.col, self.row, self.x0, self.y0 = name, col, row, x0, y0
        self.cells: list[str] = []
        self.n = 1

    def node(self, nid: str, label: str, kind: str = "proc", c: float = 0, r: float = 0, w: int | None = None, h: int | None = None) -> None:
        dw, dh = SIZES.get(kind, (190, 60))
        w, h = w or dw, h or dh
        # centrado en la celda de la grilla
        x = self.x0 + c * self.col + (210 - w) / 2
        y = self.y0 + r * self.row + (110 - h) / 2
        self.cells.append(f'<mxCell id="{nid}" value={quoteattr(label)} style="{STYLES[kind]}" vertex="1" parent="1">'
                          f'<mxGeometry x="{x:.0f}" y="{y:.0f}" width="{w}" height="{h}" as="geometry"/></mxCell>')

    def edge(self, src: str, dst: str, label: str = "", style: str = "") -> None:
        self.n += 1
        self.cells.append(f'<mxCell id="e{self.n}" value={quoteattr(label)} style="{EDGE}{style}" edge="1" parent="1" '
                          f'source="{src}" target="{dst}"><mxGeometry relative="1" as="geometry"/></mxCell>')

    def xml(self, idx: int) -> str:
        return (f'<diagram id="p{idx}" name={quoteattr(self.name)}><mxGraphModel dx="1400" dy="900" grid="1" gridSize="10" '
                f'guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="0" pageScale="1" math="0" shadow="0">'
                f'<root><mxCell id="0"/><mxCell id="1" parent="0"/>{"".join(self.cells)}</root></mxGraphModel></diagram>')


def arquitectura() -> Page:
    p = Page("1. Arquitectura", col=240, row=120, y0=90)
    p.node("t", "AsesorIA &mdash; Arquitectura", "title", 0, -0.75)
    p.node("user", "Asesor de inversiones<br>(p&aacute;gina web / cliente HTTP)", "term", 0, 2, 190, 70)
    p.node("api", "Endpoint FastAPI<br>POST /chat &middot; POST /approve<br>GET /sessions", "proc", 1, 2, 200, 70)
    p.node("svc", "Servicio del turno<br>sesi&oacute;n &middot; human-in-the-loop<br>citas verificadas &middot; guardrails de salida", "proc", 2, 2, 210, 80)
    p.node("agent", "Agente asesor<br>Microsoft Agent Framework", "agent", 3, 2, 200, 70)
    p.node("llm", "LLM (OpenAI API)<br>gpt-6-luna", "ext", 3, 0.5, 190, 60)
    p.node("mw", "Middleware de funciones<br>log de entradas y salidas<br>guardrails previos a ejecutar", "proc", 4, 2, 210, 80)
    p.node("t1", "Tool local<br><b>buscar_base_conocimiento</b>", "ok", 5.1, 0, 210, 60)
    p.node("t2", "Tools locales<br><b>registrar_perfil</b><br><b>consultar_perfil_cliente</b>", "ok", 5.1, 1, 210, 70)
    p.node("t3", "Tool local<br><b>calculadora_financiera</b>", "ok", 5.1, 2, 210, 60)
    p.node("t4", "Tool local<br><b>preparar_orden</b><br>validaci&oacute;n, advertencias y ticket", "ok", 5.1, 3, 210, 70)
    p.node("mcp", "Servidor MCP de Alpaca (stdio)<br>lista blanca de 8 tools<br>orden con aprobaci&oacute;n humana", "warn", 5.1, 4, 220, 80)
    p.node("kb", "Qdrant local<br>denso + BM25", "db", 6.3, 0)
    p.node("pol", "politicas.yaml<br>clasificaci&oacute;n de perfil<br>y l&iacute;mites", "note", 6.3, 2, 190, 80)
    p.node("alp", "Alpaca (paper trading)<br>mercado &middot; noticias<br>cuenta &middot; &oacute;rdenes", "ext", 6.3, 4, 190, 70)
    p.node("ing", "Ingesta offline<br>descarga &rarr; parseo &rarr; chunking<br>&rarr; embeddings", "proc", 6.3, -1, 210, 70)
    p.node("docs", "25 documentos p&uacute;blicos<br>SEC, ETFs, SMV, BVL", "ext", 5.1, -1, 200, 60)
    p.node("ev", "Agente evaluador<br>(proceso independiente)", "agent", 1, 4.2, 200, 70)
    p.node("judge", "Juez LLM<br>gpt-6.1-terra", "ext", 2, 5.2, 190, 60)
    p.node("out", "results.json &middot; results.csv<br>reporte.md", "note", 0, 5.2, 200, 70)
    p.node("ds", "Set de evaluaci&oacute;n<br>32 conversaciones", "note", 1, 5.4, 190, 60)
    for a, b, lab in [("user", "api", "HTTP"), ("api", "svc", ""), ("svc", "agent", ""), ("agent", "mw", "llamadas a tools"),
                      ("mw", "t1", ""), ("mw", "t2", ""), ("mw", "t3", ""), ("mw", "t4", ""), ("mw", "mcp", ""),
                      ("t1", "kb", ""), ("t2", "pol", ""), ("t4", "pol", ""), ("mcp", "alp", ""), ("ing", "kb", ""),
                      ("docs", "ing", ""), ("ev", "api", "solo HTTP"), ("ev", "judge", ""), ("ev", "out", ""), ("ds", "ev", "")]:
        p.edge(a, b, lab)
    p.edge("agent", "llm", "API", "startArrow=block;startFill=1;")
    p.edge("t4", "mcp", "precio, saldo, reloj", "dashed=1;")
    p.edge("pol", "ing", "genera documentos citables", "dashed=1;")
    return p


def mensaje() -> Page:
    p = Page("2. Flujo de un mensaje")
    p.node("t", "Recorrido de un mensaje del usuario", "title", 0, -0.6)
    p.node("lg", LEGEND, "note", 4.2, -0.4, 320, 110)
    p.node("M", "Mensaje del usuario", "term", 2, 0)
    p.node("V", "&iquest;Vac&iacute;o o<br>demasiado largo?", "code", 2, 1)
    p.node("E1", "Error 400 / 413", "stop", 3.3, 1)
    p.node("P", "&iquest;Hay una orden<br>esperando confirmaci&oacute;n?", "code", 2, 2)
    p.node("R", "Se rechaza: un mensaje nuevo<br>no es una confirmaci&oacute;n", "stop", 3.3, 2, 210, 60)
    p.node("I", "&iquest;Patrones de<br>prompt injection?", "code", 2, 3)
    p.node("F", "Se marca el turno<br>y se refuerzan las reglas", "warn", 3.3, 3, 210, 60)
    p.node("A", "El agente decide<br>qu&eacute; herramienta usar", "agent", 2, 4)
    p.node("T", "&iquest;Qu&eacute; pide<br>el usuario?", "model", 2, 5)
    p.node("KB", "buscar_base_conocimiento<br>(filtros: ticker, tipo, secci&oacute;n)", "ok", 0, 6, 210, 60)
    p.node("MK", "Herramientas MCP de Alpaca<br>precio, barras, noticias", "ok", 1, 6, 210, 60)
    p.node("PF", "&iquest;Hay perfil<br>registrado?", "code", 2.6, 6)
    p.node("D", "Declina y explica<br>el l&iacute;mite", "stop", 4.2, 6)
    p.node("S", "Responde<br>sin herramientas", "proc", 5.2, 6)
    p.node("H", "&iquest;La base devolvi&oacute;<br>fragmentos?", "code", 0, 7)
    p.node("RP", "registrar_perfil<br>el c&oacute;digo clasifica", "ok", 2.6, 7)
    p.node("ASK", "Pide capital y perfil;<br>no recomienda ni opera", "warn", 3.8, 7, 210, 60)
    p.node("C", "Responde citando<br>las fuentes S1, S2...", "proc", 0, 8.2)
    p.node("N", "&laquo;No tengo informaci&oacute;n<br>suficiente&raquo;", "warn", 1, 8.2, 200, 60)
    p.node("Q", "&iquest;Recomendaci&oacute;n<br>o compra?", "model", 2.6, 8.2)
    p.node("AN", "Mercado + documentos + calculadora<br>contrastados con los l&iacute;mites del perfil", "proc", 2.1, 9.4, 250, 60)
    p.node("ORD", "Flujo de compra<br>(p&aacute;gina 3)", "agent", 3.6, 9.4)
    p.node("OUT", "Controles de salida<br>(p&aacute;gina 4)", "agent", 2.6, 10.6)
    p.node("RES", "Respuesta + citas<br>+ perfil + traza", "term", 2.6, 11.6)
    for a, b, lab in [("M", "V", ""), ("V", "E1", "S&iacute;"), ("V", "P", "No"), ("P", "R", "S&iacute;"), ("R", "I", ""), ("P", "I", "No"),
                      ("I", "F", "S&iacute;"), ("F", "A", ""), ("I", "A", "No"), ("A", "T", ""),
                      ("T", "KB", "Hecho de un documento"), ("T", "MK", "Dato de mercado"),
                      ("T", "PF", "Recomendaci&oacute;n o compra"), ("T", "D", "Tema ajeno, venta, corto"),
                      ("T", "S", "Saludo o aclaraci&oacute;n"), ("KB", "H", ""), ("H", "C", "S&iacute;"), ("H", "N", "No"),
                      ("PF", "RP", "No, pero el mensaje<br>trae los datos"), ("PF", "ASK", "No, y faltan datos"),
                      ("PF", "Q", "S&iacute;"), ("RP", "Q", ""), ("Q", "AN", "Recomendaci&oacute;n"), ("Q", "ORD", "Compra"),
                      ("AN", "OUT", ""), ("ORD", "OUT", ""), ("C", "OUT", ""), ("N", "OUT", ""), ("MK", "OUT", ""),
                      ("D", "OUT", ""), ("S", "OUT", ""), ("ASK", "OUT", ""), ("OUT", "RES", "")]:
        p.edge(a, b, lab)
    return p


def compra() -> Page:
    p = Page("3. Flujo de compra")
    p.node("t", "Flujo de una orden de compra", "title", 0, -0.6)
    p.node("lg", LEGEND, "note", 3.4, -0.4, 320, 110)
    p.node("O", "preparar_orden<br>(s&iacute;mbolo, cantidad)", "term", 1, 0)
    p.node("P1", "&iquest;Perfil<br>registrado?", "code", 1, 1)
    p.node("RQ", "Estado: requiere_perfil<br>el agente pide los datos", "warn", 2.3, 1, 210, 60)
    p.node("U", "&iquest;Activo en el<br>universo operable?", "code", 1, 2)
    p.node("B1", "Estado: bloqueada", "stop", 2.3, 2)
    p.node("PR", "Precio real, saldo real y reloj<br>(v&iacute;a MCP de Alpaca)", "proc", 1, 3, 220, 60)
    p.node("D", "&iquest;Monto &le; poder<br>de compra?", "code", 1, 4)
    p.node("Dn", "Poder de compra = el menor entre el capital disponible del cliente y el saldo real de la cuenta", "note", -0.35, 4, 230, 90)
    p.node("B2", "Estado: bloqueada<br>sin excepci&oacute;n aunque insista", "stop", 2.3, 4, 210, 60)
    p.node("W", "&iquest;Excede l&iacute;mites<br>recomendados<br>del perfil?", "code", 1, 5, 220, 120)
    p.node("Wn", "Riesgo m&aacute;ximo por activo, tope por orden, concentraci&oacute;n por activo, exposici&oacute;n a renta variable", "note", -0.35, 5, 230, 90)
    p.node("E1", "&iquest;Primera vez<br>para esta orden?", "code", 2.3, 5)
    p.node("A1", "Estado: advertencia_1<br>aviso amable: l&iacute;mite<br>recomendado y exceso", "warn", 3.6, 5, 210, 70)
    p.node("U1", "Espera la respuesta<br>del usuario", "term", 3.6, 6.3)
    p.node("E2", "&iquest;El usuario confirm&oacute;<br>en un turno posterior?", "code", 2.3, 6.3, 220, 120)
    p.node("A2", "Estado: advertencia_2<br>riesgos y p&eacute;rdida ilustrativa<br>(como un asesor humano)", "warn", 3.6, 7.6, 210, 70)
    p.node("EX", "Se registra la<br>excepci&oacute;n de pol&iacute;tica", "warn", 2.3, 7.6)
    p.node("TK", "Ticket vigente 10 min<br>Estado: lista_para_confirmar", "ok", 1, 8.8, 220, 60)
    p.node("PS", "El agente llama a<br>place_stock_order (MCP)", "agent", 1, 9.8)
    p.node("CK", "&iquest;La llamada coincide<br>con un ticket?", "code", 1, 10.8)
    p.node("RJ", "Rechazo autom&aacute;tico,<br>sin molestar al humano", "stop", 2.3, 10.8, 210, 60)
    p.node("CARD", "Tarjeta de confirmaci&oacute;n<br>argumentos reales + validaciones<br>+ advertencias", "proc", 1, 11.9, 230, 70)
    p.node("HU", "&iquest;El humano<br>confirma?", "human", 1, 13)
    p.node("NO", "No se ejecuta nada", "stop", 2.3, 13)
    p.node("MW", "Middleware:<br>ticket vigente, solo compra<br>a mercado", "code", 1, 14.1, 230, 130)
    p.node("BL", "Orden bloqueada", "stop", 2.3, 14.1)
    p.node("AL", "Alpaca ejecuta<br>en paper trading", "ok", 1, 15.3)
    p.node("ST", "Estado de la orden<br>filled / accepted", "term", 1, 16.3)
    for a, b, lab in [("O", "P1", ""), ("P1", "RQ", "No"), ("P1", "U", "S&iacute;"), ("U", "B1", "No"), ("U", "PR", "S&iacute;"),
                      ("PR", "D", ""), ("D", "B2", "No"), ("D", "W", "S&iacute;"), ("W", "TK", "No"), ("W", "E1", "S&iacute;"),
                      ("E1", "A1", "S&iacute;"), ("A1", "U1", ""), ("E1", "E2", "No"), ("E2", "U1", "No"),
                      ("E2", "A2", "S&iacute;, tras la 1.&ordf;"), ("A2", "U1", ""), ("E2", "EX", "S&iacute;, tras la 2.&ordf;"),
                      ("EX", "TK", ""), ("TK", "PS", ""), ("PS", "CK", ""), ("CK", "RJ", "No"), ("CK", "CARD", "S&iacute;"),
                      ("CARD", "HU", ""), ("HU", "NO", "No"), ("HU", "MW", "S&iacute;"), ("MW", "BL", "Falla"),
                      ("MW", "AL", "Pasa"), ("AL", "ST", "")]:
        p.edge(a, b, lab)
    p.edge("Dn", "D", "", "dashed=1;endArrow=none;")
    p.edge("Wn", "W", "", "dashed=1;endArrow=none;")
    return p


def salida() -> Page:
    p = Page("4. Controles de salida", col=270, row=150)
    p.node("t", "Controles de salida (guardrails sobre la respuesta)", "title", 0, -0.6)
    p.node("R", "Texto del modelo", "term", 0, 0)
    p.node("C1", "&iquest;Contiene el canario<br>del prompt?", "code", 1, 0)
    p.node("X1", "Se reemplaza por una negativa<br>y se marca fuga bloqueada", "stop", 1, 1, 220, 60)
    p.node("C2", "&iquest;Cada cita S1, S2...<br>existe en la sesi&oacute;n?", "code", 2, 0)
    p.node("X2", "Se elimina la cita<br>inv&aacute;lida y se marca", "stop", 2, 1, 210, 60)
    p.node("C3", "&iquest;Consult&oacute; la base,<br>no obtuvo nada y no us&oacute;<br>otra fuente?", "code", 3, 0, 230, 130)
    p.node("X3", "Se antepone &laquo;No tengo<br>informaci&oacute;n suficiente&raquo;", "warn", 3, 1, 220, 60)
    p.node("F", "Lista de fuentes armada<br>desde la metadata,<br>nunca desde URLs del modelo", "proc", 4, 0, 220, 70)
    p.node("UI", "Interfaz: HTML saneado,<br>chips de citas, traza", "term", 5, 0, 210, 70)
    for a, b, lab in [("R", "C1", ""), ("C1", "X1", "S&iacute;"), ("C1", "C2", "No"), ("X1", "C2", ""), ("C2", "X2", "No"),
                      ("C2", "C3", "S&iacute;"), ("X2", "C3", ""), ("C3", "X3", "S&iacute;"), ("C3", "F", "No"), ("X3", "F", ""),
                      ("F", "UI", "")]:
        p.edge(a, b, lab)
    return p


def main() -> None:
    pages = [arquitectura(), mensaje(), compra(), salida()]
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n<mxfile host="app.diagrams.net" agent="AsesorIA" version="24.0.0">'
           + "".join(p.xml(i) for i, p in enumerate(pages, start=1)) + "</mxfile>\n")
    OUT.write_text(xml, encoding="utf-8")
    import xml.etree.ElementTree as ET
    root = ET.fromstring(xml.split("\n", 1)[1])            # valida que el XML este bien formado
    for d in root:
        cells = d.findall(".//mxCell")
        ids = {c.get("id") for c in cells}
        broken = [c.get("id") for c in cells if c.get("edge") and (c.get("source") not in ids or c.get("target") not in ids)]
        assert not broken, (d.get("name"), broken)
        print(f"  {d.get('name'):28s} {sum(1 for c in cells if c.get('vertex'))} nodos, {sum(1 for c in cells if c.get('edge'))} conexiones")
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
