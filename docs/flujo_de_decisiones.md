# Flujo de decisiones del agente asesor

Tres diagramas: el recorrido general de un mensaje, el detalle de una compra y los controles de salida.
Los recuadros con borde grueso son decisiones que toma el **código**; los demás, decisiones del **modelo**.

> **Versión editable:** [`diagramas.drawio`](diagramas.drawio) contiene estos diagramas y el de arquitectura en
> formato nativo de draw.io (cuatro páginas). Ábrelo en [app.diagrams.net](https://app.diagrams.net) con *Archivo > Abrir
> desde > Dispositivo*, o con draw.io Desktop. Se regenera con `python -m scripts.build_drawio`.

## 1. Recorrido de un mensaje

```mermaid
flowchart TD
    M(["Mensaje del usuario"]) --> V{{"¿Vacío o demasiado largo?"}}
    V -- "Sí" --> E1["Error 400 / 413"]
    V -- "No" --> P{{"¿Hay una orden esperando confirmación?"}}
    P -- "Sí" --> R["Se rechaza: un mensaje nuevo no es una confirmación"]
    R --> I
    P -- "No" --> I{{"¿Patrones de prompt injection?"}}
    I -- "Sí" --> F["Se marca el turno y se refuerzan las reglas"]
    F --> A
    I -- "No" --> A["El agente decide qué herramienta usar"]

    A --> T{"¿Qué pide el usuario?"}
    T -- "Hecho de un documento" --> KB["buscar_base_conocimiento<br/>(filtros: ticker, tipo, sección)"]
    T -- "Dato de mercado" --> MK["Herramientas MCP de Alpaca<br/>precio, barras, noticias"]
    T -- "Recomendación o asignación" --> PF
    T -- "Compra" --> PF
    T -- "Tema ajeno, venta, corto" --> D["Declina y explica el límite"]
    T -- "Saludo o aclaración" --> S["Responde sin herramientas"]

    KB --> H{{"¿La base devolvió fragmentos?"}}
    H -- "Sí" --> C["Responde citando las fuentes S1, S2..."]
    H -- "No" --> N["«No tengo información suficiente»"]

    PF{{"¿Hay perfil registrado?"}}
    PF -- "No, y el mensaje trae los datos" --> RP["registrar_perfil<br/>el código clasifica"]
    PF -- "No, y faltan datos" --> ASK["Pide capital y perfil;<br/>no recomienda ni opera"]
    PF -- "Sí" --> Q{"¿Recomendación o compra?"}
    RP --> Q
    Q -- "Recomendación" --> AN["Mercado + documentos + calculadora<br/>contrastados con los límites del perfil"]
    Q -- "Compra" --> ORD["Flujo de compra (diagrama 2)"]
    AN --> C

    C --> OUT["Controles de salida (diagrama 3)"]
    N --> OUT
    MK --> OUT
    D --> OUT
    S --> OUT
    ASK --> OUT
    ORD --> OUT
    OUT --> RES(["Respuesta + citas + perfil + traza"])

    classDef code stroke-width:3px;
    class V,P,I,H,PF code;
```

## 2. Flujo de compra

```mermaid
flowchart TD
    O(["preparar_orden(símbolo, cantidad)"]) --> P1{{"¿Perfil registrado?"}}
    P1 -- "No" --> RQ["Estado: requiere_perfil<br/>el agente pide los datos"]
    P1 -- "Sí" --> U{{"¿Activo en el universo operable?"}}
    U -- "No" --> B1["Estado: bloqueada"]
    U -- "Sí" --> PR["Precio real, saldo real y reloj<br/>(vía MCP de Alpaca)"]
    PR --> D{{"¿Monto ≤ poder de compra?<br/>mínimo entre capital del cliente y saldo real"}}
    D -- "No" --> B2["Estado: bloqueada<br/>sin excepción aunque insista"]
    D -- "Sí" --> W{{"¿Excede límites recomendados del perfil?<br/>riesgo, tope por orden, concentración, renta variable"}}
    W -- "No" --> TK
    W -- "Sí" --> E1{{"¿Primera vez para esta orden?"}}
    E1 -- "Sí" --> A1["Estado: advertencia_1<br/>aviso amable: límite recomendado y exceso"]
    A1 --> U1(["Espera la respuesta del usuario"])
    E1 -- "No" --> E2{{"¿El usuario confirmó en un turno posterior?"}}
    E2 -- "No" --> U1
    E2 -- "Sí, tras la 1.ª" --> A2["Estado: advertencia_2<br/>riesgos y pérdida ilustrativa"]
    A2 --> U1
    E2 -- "Sí, tras la 2.ª" --> EX["Se registra la excepción de política"]
    EX --> TK["Ticket vigente 10 min<br/>Estado: lista_para_confirmar"]

    TK --> PS["El agente llama a place_stock_order (MCP)"]
    PS --> CK{{"¿La llamada coincide con un ticket?"}}
    CK -- "No" --> RJ["Rechazo automático, sin molestar al humano"]
    CK -- "Sí" --> CARD["Tarjeta de confirmación<br/>argumentos reales + validaciones + advertencias"]
    CARD --> HU{"¿El humano confirma?"}
    HU -- "No" --> NO["No se ejecuta nada"]
    HU -- "Sí" --> MW{{"Middleware: ticket vigente,<br/>solo compra a mercado, sin parámetros exóticos"}}
    MW -- "Falla" --> BL["Orden bloqueada"]
    MW -- "Pasa" --> AL["Alpaca ejecuta en paper trading"]
    AL --> ST["Estado de la orden:<br/>filled si el mercado está abierto; accepted si está cerrado"]

    classDef code stroke-width:3px;
    class P1,U,D,W,E1,E2,CK,MW code;
```

Puntos que conviene recordar:

- El modelo no puede avanzar dos etapas de advertencia en el mismo turno: cada avance exige un mensaje posterior del
  usuario.
- El framework impide que los argumentos cambien después de la aprobación: lo que el humano confirma es exactamente
  lo que se ejecuta.
- El agente no tiene herramientas de venta, cancelación, opciones ni cripto: no están en la lista blanca.

## 3. Controles de salida

```mermaid
flowchart LR
    R(["Texto del modelo"]) --> C1{{"¿Contiene el canario del prompt?"}}
    C1 -- "Sí" --> X1["Se reemplaza por una negativa<br/>y se marca fuga bloqueada"]
    C1 -- "No" --> C2{{"¿Cada cita S1, S2... existe en la sesión?"}}
    X1 --> C2
    C2 -- "No" --> X2["Se elimina la cita inválida y se marca"]
    C2 -- "Sí" --> C3
    X2 --> C3{{"¿Consultó la base, no obtuvo nada<br/>y no usó otra fuente de datos?"}}
    C3 -- "Sí" --> X3["Se antepone<br/>«No tengo información suficiente»"]
    C3 -- "No" --> F
    X3 --> F["Lista de fuentes armada desde la metadata,<br/>nunca desde URLs del modelo"]
    F --> UI(["Interfaz: HTML saneado, chips de citas, traza"])

    classDef code stroke-width:3px;
    class C1,C2,C3 code;
```
