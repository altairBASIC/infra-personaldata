"""Ingesta: lee un archivo .mbox desde disco y lo sube a MinIO Bronze."""

from __future__ import annotations

import time
from pathlib import Path

from pipeline.utils.logging_cfg import get_logger
from pipeline.utils.minio_client import subir_archivo

logger = get_logger("ingesta")


def ingestar_mbox(
    ruta_mbox: Path,
    run_id: str,
    bucket: str = "bronze",
) -> tuple[str, int]:
    """Sube un archivo .mbox a MinIO Bronze sin transformar contenido.

    Args:
        ruta_mbox: Ruta local al archivo .mbox.
        run_id: UUID del run de ingesta.
        bucket: Nombre del bucket de destino.

    Returns:
        Tupla (uri_bronze, tamaño_bytes).

    Raises:
        FileNotFoundError: Si el archivo .mbox no existe.
    """
    if not ruta_mbox.exists():
        raise FileNotFoundError(f"Archivo mbox no encontrado: {ruta_mbox}")

    inicio = time.monotonic()
    tamaño = ruta_mbox.stat().st_size
    objeto = f"mail/{run_id}/raw.mbox"
    uri = subir_archivo(bucket, objeto, ruta_mbox)
    duracion = time.monotonic() - inicio

    logger.info(
        "Ingesta completada: %d bytes en %.2fs → %s",
        tamaño,
        duracion,
        uri,
    )
    return uri, tamaño
