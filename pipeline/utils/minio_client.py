"""Wrapper para MinIO con autenticación por variables de entorno."""

from __future__ import annotations

import io
import os
from pathlib import Path

from minio import Minio
from minio.error import S3Error

from pipeline.utils.logging_cfg import get_logger

logger = get_logger("minio_client")


def _get_client() -> Minio:
    """Crea un cliente MinIO a partir de variables de entorno."""
    return Minio(
        endpoint=os.environ.get("MINIO_ENDPOINT", "minio:9000"),
        access_key=os.environ.get("MINIO_ACCESS_KEY", "minioadmin"),
        secret_key=os.environ.get("MINIO_SECRET_KEY", "minioadmin"),
        secure=os.environ.get("MINIO_SECURE", "false").lower() == "true",
    )


def asegurar_bucket(nombre: str) -> None:
    """Crea el bucket si no existe.

    Args:
        nombre: Nombre del bucket a verificar/crear.
    """
    client = _get_client()
    if not client.bucket_exists(nombre):
        client.make_bucket(nombre)
        logger.info("Bucket '%s' creado", nombre)


def subir_archivo(bucket: str, objeto: str, ruta_local: Path) -> str:
    """Sube un archivo local a MinIO.

    Args:
        bucket: Nombre del bucket destino.
        objeto: Ruta del objeto dentro del bucket.
        ruta_local: Ruta local del archivo a subir.

    Returns:
        URI s3 del objeto subido.
    """
    client = _get_client()
    asegurar_bucket(bucket)
    client.fput_object(bucket, objeto, str(ruta_local))
    uri = f"s3://{bucket}/{objeto}"
    logger.info("Archivo subido: %s → %s", ruta_local, uri)
    return uri


def descargar_bytes(bucket: str, objeto: str) -> bytes:
    """Descarga un objeto de MinIO como bytes.

    Args:
        bucket: Nombre del bucket.
        objeto: Ruta del objeto dentro del bucket.

    Returns:
        Contenido del objeto en bytes.
    """
    client = _get_client()
    response = client.get_object(bucket, objeto)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()


def subir_bytes(bucket: str, objeto: str, datos: bytes) -> str:
    """Sube datos en bytes a MinIO.

    Args:
        bucket: Nombre del bucket destino.
        objeto: Ruta del objeto dentro del bucket.
        datos: Contenido a subir.

    Returns:
        URI s3 del objeto subido.
    """
    client = _get_client()
    asegurar_bucket(bucket)
    client.put_object(
        bucket,
        objeto,
        io.BytesIO(datos),
        length=len(datos),
    )
    uri = f"s3://{bucket}/{objeto}"
    logger.info("Bytes subidos: %d bytes → %s", len(datos), uri)
    return uri
