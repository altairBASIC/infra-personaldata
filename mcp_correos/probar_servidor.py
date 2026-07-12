"""Verificacion aislada del servidor MCP, sin ningun agente de por medio.

Levanta el servidor por stdio como lo haria un agente real, y comprueba:

  1. que el servidor inicializa,
  2. que lista las dos tools esperadas,
  3. que buscar_correos devuelve resultados reales desde Chroma,
  4. que consultar_senales devuelve senales reales desde Silver.

Requiere la infraestructura levantada (API en localhost:8000).

Uso:
    .venv-mcp/bin/python -m mcp_correos.probar_servidor
"""

from __future__ import annotations

import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVIDOR = StdioServerParameters(
    command=sys.executable,
    args=["-m", "mcp_correos.servidor"],
)


def _mostrar(titulo: str, contenido: object) -> None:
    print(f"\n=== {titulo} ===")
    print(json.dumps(contenido, indent=2, ensure_ascii=False))


async def main() -> int:
    async with stdio_client(SERVIDOR) as (lectura, escritura):
        async with ClientSession(lectura, escritura) as sesion:
            await sesion.initialize()
            print("Servidor MCP inicializado.")

            tools = await sesion.list_tools()
            nombres = sorted(t.name for t in tools.tools)
            _mostrar("Tools expuestas", nombres)
            esperadas = ["buscar_correos", "consultar_senales"]
            if nombres != esperadas:
                print(f"FALLO: se esperaban {esperadas}")
                return 1

            resultado = await sesion.call_tool(
                "buscar_correos",
                {"query": "mantenimiento de la base de datos", "top_k": 3},
            )
            datos = json.loads(resultado.content[0].text)
            _mostrar("buscar_correos('mantenimiento de la base de datos', 3)", datos)
            if "error" in datos or not datos.get("results"):
                print("FALLO: buscar_correos no devolvio resultados")
                return 1

            resultado = await sesion.call_tool(
                "consultar_senales",
                {"actor": "ana@ejemplo.com", "limit": 5},
            )
            datos = json.loads(resultado.content[0].text)
            _mostrar("consultar_senales(actor='ana@ejemplo.com', 5)", datos)
            if "error" in datos or datos.get("total", 0) < 1:
                print("FALLO: consultar_senales no devolvio senales")
                return 1

    print("\nVERIFICACION OK: las dos tools responden con datos reales.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
