"""Orquestador principal del pipeline Bronze → Silver → Chroma."""

from __future__ import annotations

import os
import time
from pathlib import Path
from uuid import uuid4

from pipeline.etapas.calidad import aplica_todas, escribir_reporte
from pipeline.etapas.embeddings import indexar_en_chroma
from pipeline.etapas.ingesta import ingestar_mbox
from pipeline.etapas.normaliza import (
    escribir_silver,
    normalizar_desde_bronze,
    normalizar_mbox_desde_archivo,
)
from pipeline.metadata.linaje import LinajeWriter
from pipeline.utils.logging_cfg import configurar_logging, get_logger

logger = get_logger("main")


def ejecutar_pipeline(
    ruta_mbox: Path | None = None,
    silver_base: Path | None = None,
    chroma_path: Path | None = None,
    metrics_path: Path | None = None,
    linaje_path: Path | None = None,
    run_id: str | None = None,
    usar_minio: bool = True,
) -> dict:
    """Ejecuta el pipeline completo: ingesta → normaliza → calidad → embeddings.

    Args:
        ruta_mbox: Ruta al archivo .mbox de entrada.
        silver_base: Directorio base para Silver Parquet.
        chroma_path: Directorio para Chroma.
        metrics_path: Directorio para reportes de calidad.
        linaje_path: Ruta para linaje.json.
        run_id: UUID del run. Se genera uno si es ``None``.
        usar_minio: Si es ``True``, sube a MinIO Bronze y descarga.

    Returns:
        Diccionario de linaje del run.
    """
    nivel = os.environ.get("LOG_LEVEL", "INFO")
    configurar_logging(nivel)

    rid = run_id or str(uuid4())
    mbox = ruta_mbox or Path(os.environ.get("MBOX_PATH", "/app/data/input/correos.mbox"))
    silver = silver_base or Path(os.environ.get("SILVER_PATH", "/app/data/silver"))
    chroma = chroma_path or Path(os.environ.get("CHROMA_PATH", "/app/data/chroma"))
    metrics = metrics_path or Path(os.environ.get("METRICS_PATH", "/app/data/metrics"))
    linaje_out = linaje_path or Path(os.environ.get("LINAJE_PATH", "/app/data/linaje.json"))

    linaje = LinajeWriter(ruta_salida=linaje_out, run_id=rid)
    logger.info("Iniciando pipeline run_id=%s", rid)

    # --- Etapa 1: Ingesta ---
    t0 = time.monotonic()
    if usar_minio:
        uri_bronze, tamaño = ingestar_mbox(mbox, rid)
        duracion_ingesta = time.monotonic() - t0

        import mailbox as mb
        mbox_count = sum(1 for _ in mb.mbox(str(mbox)))

        linaje.registrar_etapa(
            etapa="ingesta",
            input_path=str(mbox),
            output_path=uri_bronze,
            filas_leidas=mbox_count,
            filas_escritas=mbox_count,
            duracion_s=duracion_ingesta,
        )

        # --- Etapa 2: Normalización desde Bronze ---
        t1 = time.monotonic()
        objeto = f"mail/{rid}/raw.mbox"
        df = normalizar_desde_bronze("bronze", objeto, rid)
    else:
        import mailbox as mb
        mbox_count = sum(1 for _ in mb.mbox(str(mbox)))
        duracion_ingesta = time.monotonic() - t0

        linaje.registrar_etapa(
            etapa="ingesta",
            input_path=str(mbox),
            output_path=f"local:{mbox}",
            filas_leidas=mbox_count,
            filas_escritas=mbox_count,
            duracion_s=duracion_ingesta,
        )

        t1 = time.monotonic()
        df = normalizar_mbox_desde_archivo(mbox, rid)

    filas_normalizadas = len(df)

    # --- Etapa 3: Calidad ---
    t2 = time.monotonic()
    total_pre = len(df)
    df_valido, descartadas = aplica_todas(df)
    duracion_calidad = time.monotonic() - t2

    duracion_normaliza = time.monotonic() - t1
    linaje.registrar_etapa(
        etapa="normaliza",
        input_path=f"s3://bronze/mail/{rid}/raw.mbox" if usar_minio else str(mbox),
        output_path=str(silver / "mail"),
        filas_leidas=filas_normalizadas,
        filas_escritas=len(df_valido),
        duracion_s=duracion_normaliza,
        descartadas_por_regla=descartadas,
    )

    escribir_reporte(
        total_entrada=total_pre,
        total_validas=len(df_valido),
        descartadas_por_regla=descartadas,
        ruta_salida=metrics / "reporte_calidad.json",
    )

    # --- Etapa 4: Escribir Silver ---
    rutas_silver = escribir_silver(df_valido, silver)

    # --- Etapa 5: Embeddings ---
    t3 = time.monotonic()
    total_indexados = indexar_en_chroma(df_valido, chroma)
    duracion_embeddings = time.monotonic() - t3

    linaje.registrar_etapa(
        etapa="embeddings",
        input_path=str(silver / "mail"),
        output_path=str(chroma),
        filas_leidas=len(df_valido),
        filas_escritas=total_indexados,
        duracion_s=duracion_embeddings,
    )

    resultado = linaje.cerrar()
    logger.info("Pipeline completado: %d señales válidas indexadas", len(df_valido))
    return resultado


if __name__ == "__main__":
    ejecutar_pipeline()
