"""
gold.py — Etapa Silver → Gold (5 tablas + linaje + reporte de calidad)

La zona Gold contiene tablas de resumen ("features") listas para consumir,
construidas agregando Silver con DuckDB (consultas GROUP BY).

Además:
  - Linaje: cada tabla se registra (trazabilidad: qué se leyó/escribió, cuánto tardó).
  - Reporte de calidad: chequeo de salud de las tablas (vacías, coherencia, veredicto).

Tablas generadas:
  1. actividad_por_actor    — quién escribe más (frecuencia)
  2. volumen_por_mes        — evolución del correo en el tiempo
  3. distribucion_por_canal — qué tipo de correo predomina
  4. recencia_por_actor     — última vez que se supo de cada contacto
  5. resumen_general        — totales globales (vista panorámica)
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import duckdb

from pipeline.metadata.linaje import LinajeWriter


def _silver_glob() -> str:
    """Ruta glob de los Parquet de Silver (lee todas las particiones)."""
    base = Path(os.environ.get("SILVER_PATH", "/app/data/silver"))
    return str(base / "**" / "*.parquet")


def _gold_dir() -> Path:
    """Carpeta donde se escriben los Parquet de Gold."""
    return Path(os.environ.get("GOLD_PATH", "/app/data/gold"))


def _linaje_path() -> Path:
    """Ruta del archivo de linaje JSON."""
    return Path(os.environ.get("LINAJE_PATH", "/app/data/linaje.json"))


def _reporte_path() -> Path:
    """Ruta del reporte de calidad de Gold."""
    return Path(os.environ.get("METRICS_PATH", "/app/data/metrics")) / "reporte_gold.json"


def _ejecutar_tabla(con: duckdb.DuckDBPyConnection, nombre: str,
                    consulta: str) -> tuple[int, float]:
    """Ejecuta una consulta, guarda el resultado como Parquet y mide tiempo.

    Devuelve (filas_escritas, duracion_s) para registrar en el linaje.
    """
    inicio = time.perf_counter()
    df = con.execute(consulta).pl()
    salida = _gold_dir() / f"{nombre}.parquet"
    df.write_parquet(salida)
    duracion = time.perf_counter() - inicio

    print(f"  tabla '{nombre}': {len(df)} filas -> {salida.name} ({duracion:.3f}s)")
    return len(df), duracion


def escribir_reporte_calidad(con: duckdb.DuckDBPyConnection,
                             nombres_tablas: list[str]) -> dict:
    """Construye un reporte de salud de las tablas Gold generadas.

    Lee de vuelta los Parquet recién creados para inventariarlos,
    detectar tablas vacías y verificar coherencia entre tablas.
    """
    gold = _gold_dir()

    # 1. INVENTARIO: cuántas filas tiene cada tabla
    inventario = {}
    for nombre in nombres_tablas:
        ruta = gold / f"{nombre}.parquet"
        filas = con.execute(f"SELECT COUNT(*) FROM read_parquet('{ruta}')").fetchone()[0]
        inventario[nombre] = filas

    # 2. TABLAS VACÍAS: las que tienen 0 filas (señal de alarma)
    tablas_vacias = [n for n, filas in inventario.items() if filas == 0]

    # 3. COHERENCIA: cruzar números que deberían concordar
    resumen_ruta = gold / "resumen_general.parquet"
    resumen = con.execute(f"SELECT * FROM read_parquet('{resumen_ruta}')").pl()
    total_contactos = resumen["total_contactos"][0]
    total_canales = resumen["total_canales"][0]

    coherencia = {
        "contactos_cuadran": {
            "esperado": int(total_contactos),
            "actividad_por_actor": inventario.get("actividad_por_actor", 0),
            "recencia_por_actor": inventario.get("recencia_por_actor", 0),
            "ok": (total_contactos == inventario.get("actividad_por_actor")
                   == inventario.get("recencia_por_actor")),
        },
        "canales_cuadran": {
            "esperado": int(total_canales),
            "distribucion_por_canal": inventario.get("distribucion_por_canal", 0),
            "ok": total_canales == inventario.get("distribucion_por_canal"),
        },
    }

    # 4. VEREDICTO: todo ok solo si no hay vacías y toda la coherencia pasa
    todo_ok = (not tablas_vacias
               and coherencia["contactos_cuadran"]["ok"]
               and coherencia["canales_cuadran"]["ok"])

    reporte = {
        "tablas_generadas": len(inventario),
        "inventario": inventario,
        "tablas_vacias": tablas_vacias,
        "coherencia": coherencia,
        "veredicto": "todo_ok" if todo_ok else "hay_problemas",
    }

    ruta = _reporte_path()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(reporte, f, indent=2, ensure_ascii=False)

    estado = "OK" if todo_ok else "PROBLEMAS"
    print(f"  reporte de calidad: {estado} -> {ruta.name}")
    return reporte


def ejecutar_gold(run_id: str | None = None,
                  linaje: LinajeWriter | None = None) -> None:
    """Orquesta la construcción de las tablas Gold, el linaje y el reporte.

    Args:
        run_id: identificador del run. Solo se usa si esta función crea su
            propio linaje (cuando ``linaje`` es None).
        linaje: un LinajeWriter ya existente. Si se pasa, Gold registra sus
            etapas en él y NO lo cierra (lo cierra quien lo creó). Si es None,
            Gold crea su propio linaje y lo cierra al terminar. Esto permite
            tanto correr Gold de forma independiente como integrarlo en un
            pipeline mayor que comparte un único linaje.
    """
    silver = _silver_glob()
    gold_dir = _gold_dir()
    gold_dir.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(":memory:")

    # Filas del Silver de entrada (igual para todas las tablas)
    filas_silver = con.execute(
        f"SELECT COUNT(*) FROM read_parquet('{silver}')"
    ).fetchone()[0]

    # Si nos pasan un linaje, lo usamos (y NO lo cerramos al final).
    # Si no, creamos el nuestro y lo cerramos nosotros.
    linaje_propio = linaje is None
    if linaje_propio:
        linaje = LinajeWriter(_linaje_path(), run_id)

    print("Construyendo zona Gold...")

    tablas = {
        "actividad_por_actor": f"""
            SELECT actor, COUNT(*) AS total_correos
            FROM read_parquet('{silver}')
            GROUP BY actor
            ORDER BY total_correos DESC
        """,
        "volumen_por_mes": f"""
            SELECT date_trunc('month', timestamp) AS mes, COUNT(*) AS total_correos
            FROM read_parquet('{silver}')
            GROUP BY mes
            ORDER BY mes
        """,
        "distribucion_por_canal": f"""
            SELECT channel, COUNT(*) AS total_correos
            FROM read_parquet('{silver}')
            GROUP BY channel
            ORDER BY total_correos DESC
        """,
        "recencia_por_actor": f"""
            SELECT actor, MAX(timestamp) AS ultimo_contacto, COUNT(*) AS total_correos
            FROM read_parquet('{silver}')
            GROUP BY actor
            ORDER BY ultimo_contacto DESC
        """,
        "resumen_general": f"""
            SELECT
                COUNT(*) AS total_correos,
                COUNT(DISTINCT actor) AS total_contactos,
                COUNT(DISTINCT channel) AS total_canales,
                MIN(timestamp) AS primer_correo,
                MAX(timestamp) AS ultimo_correo
            FROM read_parquet('{silver}')
        """,
    }

    for nombre, consulta in tablas.items():
        filas_escritas, duracion = _ejecutar_tabla(con, nombre, consulta)
        linaje.registrar_etapa(
            etapa=f"gold_{nombre}",
            input_path=silver,
            output_path=str(_gold_dir() / f"{nombre}.parquet"),
            filas_leidas=filas_silver,
            filas_escritas=filas_escritas,
            duracion_s=duracion,
        )

    # Reporte de calidad: revisa las tablas recién generadas
    escribir_reporte_calidad(con, list(tablas.keys()))

    con.close()
    # Solo cerramos el linaje si lo creamos nosotros.
    if linaje_propio:
        linaje.cerrar()
    print("Gold completado. Linaje y reporte registrados.")


if __name__ == "__main__":
    ejecutar_gold()