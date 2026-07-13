"""Normalización: parsea mbox desde Bronze y construye el esquema unificado Silver."""

from __future__ import annotations

import email
import email.policy
import email.utils
import mailbox
import re
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import polars as pl
from bs4 import BeautifulSoup

from pipeline.utils.logging_cfg import get_logger
from pipeline.utils.minio_client import descargar_bytes

logger = get_logger("normaliza")

NAMESPACE_SIGNAL = uuid.NAMESPACE_URL


def _generar_signal_id(source: str, raw_id: str) -> str:
    """Genera un signal_id determinístico con UUID v5."""
    return str(uuid.uuid5(NAMESPACE_SIGNAL, source + raw_id))


def _extraer_texto_plano(payload: str) -> str:
    """Convierte HTML a texto plano preservando saltos de línea."""
    if "<html" in payload.lower() or "<body" in payload.lower() or "<div" in payload.lower():
        soup = BeautifulSoup(payload, "lxml")
        for br in soup.find_all("br"):
            br.replace_with("\n")
        for p in soup.find_all("p"):
            p.insert_after("\n")
        return soup.get_text(separator="\n").strip()
    return payload.strip()


def _decodificar_payload(msg: email.message.Message) -> str:
    """Extrae el cuerpo de texto de un mensaje, manejando codificaciones mixtas."""
    if msg.is_multipart():
        partes_texto: list[str] = []
        for parte in msg.walk():
            content_type = parte.get_content_type()
            if content_type in ("text/plain", "text/html"):
                charset = parte.get_content_charset() or "utf-8"
                raw = parte.get_payload(decode=True)
                if raw is None:
                    continue
                for enc in (charset, "utf-8", "iso-8859-1", "windows-1252"):
                    try:
                        texto = raw.decode(enc)
                        if content_type == "text/html":
                            texto = _extraer_texto_plano(texto)
                        partes_texto.append(texto)
                        break
                    except (UnicodeDecodeError, LookupError):
                        continue
                else:
                    partes_texto.append("")
        return "\n".join(partes_texto).strip()

    charset = msg.get_content_charset() or "utf-8"
    raw = msg.get_payload(decode=True)
    if raw is None:
        return ""
    for enc in (charset, "utf-8", "iso-8859-1", "windows-1252"):
        try:
            texto = raw.decode(enc)
            if msg.get_content_type() == "text/html":
                texto = _extraer_texto_plano(texto)
            return texto.strip()
        except (UnicodeDecodeError, LookupError):
            continue
    return ""


def _parsear_fecha(date_str: str | None) -> datetime | None:
    """Parsea la cabecera Date de un email a datetime UTC."""
    if not date_str:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(date_str)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def _normalizar_actor(from_header: str | None) -> str:
    """Extrae y normaliza el email del remitente."""
    if not from_header:
        return ""
    _, addr = email.utils.parseaddr(from_header)
    return addr.lower().strip()


def normalizar_mbox_desde_archivo(
    ruta_mbox: Path,
    run_id: str,
    source: str = "mail",
) -> pl.DataFrame:
    """Parsea un archivo .mbox local y retorna un DataFrame con el esquema unificado.

    Args:
        ruta_mbox: Ruta al archivo .mbox.
        run_id: UUID del run de ingesta.
        source: Identificador de fuente.

    Returns:
        DataFrame de Polars con el esquema Silver.
    """
    inicio = time.monotonic()
    mbox = mailbox.mbox(str(ruta_mbox))

    registros: list[dict[str, Any]] = []
    for msg in mbox:
        raw_id = msg.get("Message-ID", "") or ""
        raw_id = raw_id.strip()
        if not raw_id:
            raw_id = f"sin-id-{len(registros)}"

        actor = _normalizar_actor(msg.get("From"))
        timestamp = _parsear_fecha(msg.get("Date"))
        content_text = _decodificar_payload(msg)
        signal_id = _generar_signal_id(source, raw_id)
        channel = msg.get("X-Gmail-Labels", "") or ""

        subject = msg.get("Subject", "") or ""
        content_meta: dict[str, str] = {}
        if subject:
            content_meta["subject"] = subject

        registros.append({
            "signal_id": signal_id,
            "timestamp": timestamp,
            "source": source,
            "actor": actor,
            "channel": channel if channel else None,
            "content_text": content_text,
            "content_meta": str(content_meta) if content_meta else None,
            "entities": None,
            "raw_id": raw_id,
            "ingest_run_id": run_id,
        })

    mbox.close()
    duracion = time.monotonic() - inicio
    logger.info(
        "Normalización: %d mensajes parseados en %.2fs",
        len(registros),
        duracion,
    )

    if not registros:
        return pl.DataFrame(
            schema={
                "signal_id": pl.Utf8,
                "timestamp": pl.Datetime("us", "UTC"),
                "source": pl.Utf8,
                "actor": pl.Utf8,
                "channel": pl.Utf8,
                "content_text": pl.Utf8,
                "content_meta": pl.Utf8,
                "entities": pl.List(pl.Utf8),
                "raw_id": pl.Utf8,
                "ingest_run_id": pl.Utf8,
            }
        )

    df = pl.DataFrame(registros)
    # Casts explícitos al tipo del catálogo: con columnas 100% nulas Polars
    # infiere Null y el Parquet quedaría tipado INT32 en vez de string.
    df = df.with_columns(
        pl.col("timestamp").cast(pl.Datetime("us", "UTC")),
        pl.col("channel").cast(pl.Utf8),
        pl.col("entities").cast(pl.List(pl.Utf8)),
    )
    return df


def normalizar_desde_bronze(
    bucket: str,
    objeto: str,
    run_id: str,
    source: str = "mail",
) -> pl.DataFrame:
    """Descarga mbox de MinIO Bronze y normaliza.

    Args:
        bucket: Bucket de MinIO.
        objeto: Ruta del objeto en MinIO.
        run_id: UUID del run.
        source: Identificador de fuente.

    Returns:
        DataFrame de Polars con el esquema Silver.
    """
    datos = descargar_bytes(bucket, objeto)
    with tempfile.NamedTemporaryFile(suffix=".mbox", delete=False) as tmp:
        tmp.write(datos)
        tmp_path = Path(tmp.name)

    try:
        return normalizar_mbox_desde_archivo(tmp_path, run_id, source)
    finally:
        tmp_path.unlink(missing_ok=True)


def escribir_silver(
    df: pl.DataFrame,
    silver_base: Path,
    source: str = "mail",
) -> list[Path]:
    """Escribe el DataFrame Silver como Parquet particionado por año/mes.

    Args:
        df: DataFrame validado.
        silver_base: Directorio base para Silver.
        source: Nombre de la fuente.

    Returns:
        Lista de rutas de archivos Parquet escritos.
    """
    if df.is_empty():
        logger.warning("DataFrame vacío, no se escriben archivos Silver")
        return []

    df = df.with_columns([
        pl.col("timestamp").dt.year().alias("year"),
        pl.col("timestamp").dt.month().alias("month"),
    ])

    rutas_escritas: list[Path] = []
    for (year, month), grupo in df.group_by(["year", "month"]):
        dir_part = silver_base / source / f"year={year}" / f"month={month:02d}"
        dir_part.mkdir(parents=True, exist_ok=True)
        ruta = dir_part / "data.parquet"
        grupo.drop(["year", "month"]).write_parquet(ruta)
        rutas_escritas.append(ruta)
        logger.info("Silver escrito: %s (%d filas)", ruta, len(grupo))

    return rutas_escritas
