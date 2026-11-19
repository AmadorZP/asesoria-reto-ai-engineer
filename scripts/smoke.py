"""Prueba de humo en vivo: OpenAI + Agent Framework + servidor MCP de Alpaca.

    python -m scripts.smoke
"""
from __future__ import annotations

import asyncio
import time

from agent_framework import Agent, tool
from agent_framework.openai import OpenAIChatClient

from advisor.config import ADVISOR_MODEL
from advisor.mcp_alpaca import build_alpaca_tool, verify_alpaca_tool


@tool(approval_mode="never_require")
def sumar(a: float, b: float) -> float:
    """Suma dos numeros."""
    return a + b


async def main() -> None:
    client = OpenAIChatClient(model=ADVISOR_MODEL)

    print(f"== 1. OpenAI ({ADVISOR_MODEL}) con tool local ==")
    agent = Agent(client=client, instructions="Responde en espanol, muy breve. Usa la herramienta para sumar.",
                  tools=[sumar], default_options={"store": False})
    session = agent.create_session(session_id="smoke")
    t = time.time()
    r = await agent.run("Cuanto es 1234.5 + 765.5?", session=session)
    print("  respuesta:", r.text, f"({time.time() - t:.1f}s)")
    r = await agent.run("Y si a eso le sumas 1000?", session=session)
    print("  memoria de sesion:", r.text)

    print("== 2. Servidor MCP de Alpaca ==")
    alpaca = build_alpaca_tool()
    t = time.time()
    async with alpaca:
        modes = verify_alpaca_tool(alpaca)
        print(f"  conectado en {time.time() - t:.1f}s; herramientas expuestas y modo de aprobacion:")
        for name, mode in modes.items():
            print(f"    {name:22s} {mode}")
        agent2 = Agent(client=client, tools=[alpaca], default_options={"store": False},
                       instructions="Responde en espanol, breve. Para precios usa feed='iex'.")
        t = time.time()
        r = await agent2.run("Dime si el mercado esta abierto, mi poder de compra y el ultimo precio de MSFT.")
        print("  respuesta:", r.text, f"({time.time() - t:.1f}s)")
        print("  uso de tokens:", r.usage_details)


if __name__ == "__main__":
    asyncio.run(main())
