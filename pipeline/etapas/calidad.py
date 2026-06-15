"""Reglas de calidad declarativas con patrón registry de decoradores."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

import polars as pl
import yaml

from pipeline.utils.logging_cfg import get_logger

logger = get_logger("calidad")

NAMESPACE_SIGNAL = uuid.NAMESPACE_URL

ReglaFn = Callable[[pl.DataFrame], pl.DataFrame]
_REGISTRY: dict[str, ReglaFn] = {}


def regla(id_regla: str) -> Callable[[ReglaFn], ReglaFn]:
    """Decorador que registra una función como regla de calidad.

    Args:
        id_regla: Identificador único de la regla (e.g. ``r01_actor_email_valido``).
    """
    def wrapper(fn: ReglaFn) -> ReglaFn:
        _REGISTRY[id_regla] = fn
        return fn
    return wrapper


@regla("r01_actor_email_valido")
def r01_actor_email_valido(df: pl.DataFrame) -> pl.DataFrame:
    """actor debe cumplir formato de email RFC 5322 simplificado."""
    patron = r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"
    return df.with_columns(
        pl.col("actor").str.contains(patron).alias("valida_r01_actor_email_valido")
    )


@regla("r02_timestamp_valido")
def r02_timestamp_valido(df: pl.DataFrame) -> pl.DataFrame:
    """timestamp no nulo, no futuro (> ahora + 1 día), no anterior a 2000-01-01."""
    ahora = datetime.now(timezone.utc)
    limite_futuro = ahora + timedelta(days=1)
    limite_pasado = datetime(2000, 1, 1, tzinfo=timezone.utc)

    return df.with_columns(
        (
            pl.col("timestamp").is_not_null()
            & (pl.col("timestamp") <= limite_futuro)
            & (pl.col("timestamp") >= limite_pasado)
        ).alias("valida_r02_timestamp_valido")
    )


@regla("r03_content_no_vacio")
def r03_content_no_vacio(df: pl.DataFrame) -> pl.DataFrame:
    """content_text con longitud > 10 caracteres tras strip."""
    return df.with_columns(
        (
            pl.col("content_text").is_not_null()
            & (pl.col("content_text").str.strip_chars().str.len_chars() > 10)
        ).alias("valida_r03_content_no_vacio")
    )


@regla("r04_raw_id_unico")
def r04_raw_id_unico(df: pl.DataFrame) -> pl.DataFrame:
    """raw_id no debe repetirse en el mismo run."""
    conteo = df.group_by("raw_id").len().rename({"len": "conteo_raw_id"})
    df_con_conteo = df.join(conteo, on="raw_id", how="left")
    return df_con_conteo.with_columns(
        (pl.col("conteo_raw_id") == 1).alias("valida_r04_raw_id_unico")
    ).drop("conteo_raw_id")


@regla("r05_encoding_valido")
def r05_encoding_valido(df: pl.DataFrame) -> pl.DataFrame:
    """content_text debe ser UTF-8 válido (no vacío tras decodificación)."""
    return df.with_columns(
        (
            pl.col("content_text").is_not_null()
            & (pl.col("content_text").str.len_chars() > 0)
        ).alias("valida_r05_encoding_valido")
    )


@regla("r06_signal_id_deterministico")
def r06_signal_id_deterministico(df: pl.DataFrame) -> pl.DataFrame:
    """signal_id == uuid5(NAMESPACE_URL, source + raw_id)."""
    esperado = df.select(
        pl.struct(["source", "raw_id"]).map_elements(
            lambda row: str(uuid.uuid5(NAMESPACE_SIGNAL, row["source"] + row["raw_id"])),
            return_dtype=pl.Utf8,
        ).alias("signal_id_esperado")
    ).to_series()

    return df.with_columns(
        (pl.col("signal_id") == esperado).alias("valida_r06_signal_id_deterministico")
    )


def obtener_reglas_activas(ruta_reglas: Path | None = None) -> list[str]:
    """Lee reglas_calidad.yaml y retorna los IDs de reglas activas.

    Args:
        ruta_reglas: Ruta al archivo YAML. Usa la ruta por defecto si es ``None``.

    Returns:
        Lista de IDs de reglas.
    """
    ruta = ruta_reglas or Path(__file__).resolve().parent.parent.parent / "reglas_calidad.yaml"
    with open(ruta, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return [r["id"] for r in config.get("reglas", [])]


def aplica_todas(
    df: pl.DataFrame,
    ruta_reglas: Path | None = None,
) -> tuple[pl.DataFrame, dict[str, int]]:
    """Aplica todas las reglas registradas y retorna filas válidas + conteo de descartadas.

    Args:
        df: DataFrame con esquema Silver.
        ruta_reglas: Ruta al YAML de reglas (opcional).

    Returns:
        Tupla (DataFrame con solo filas válidas, dict de descartadas por regla).
    """
    ids_activas = obtener_reglas_activas(ruta_reglas)
    total_entrada = len(df)
    descartadas: dict[str, int] = {}

    for id_regla in ids_activas:
        if id_regla not in _REGISTRY:
            logger.warning("Regla '%s' declarada en YAML pero no implementada", id_regla)
            continue
        fn = _REGISTRY[id_regla]
        df = fn(df)

    columnas_valida = [c for c in df.columns if c.startswith("valida_")]

    for col in columnas_valida:
        id_r = col.replace("valida_", "")
        invalidas = df.filter(~pl.col(col)).height
        if invalidas > 0:
            descartadas[id_r] = invalidas

    if columnas_valida:
        mascara = pl.col(columnas_valida[0])
        for col in columnas_valida[1:]:
            mascara = mascara & pl.col(col)
        df_validas = df.filter(mascara).drop(columnas_valida)
    else:
        df_validas = df

    logger.info(
        "Calidad: %d entrada → %d válidas (%d descartadas)",
        total_entrada,
        len(df_validas),
        total_entrada - len(df_validas),
    )
    return df_validas, descartadas


def escribir_reporte(
    total_entrada: int,
    total_validas: int,
    descartadas_por_regla: dict[str, int],
    ruta_salida: Path,
) -> None:
    """Escribe el reporte de calidad como JSON.

    Args:
        total_entrada: Total de filas de entrada.
        total_validas: Total de filas válidas tras aplicar reglas.
        descartadas_por_regla: Conteo de descartadas por cada regla.
        ruta_salida: Ruta del archivo de reporte.
    """
    tasa_error = (total_entrada - total_validas) / total_entrada if total_entrada > 0 else 0.0
    reporte = {
        "total_entrada": total_entrada,
        "total_validas": total_validas,
        "descartadas_por_regla": descartadas_por_regla,
        "tasa_error_global": round(tasa_error, 4),
    }
    ruta_salida.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta_salida, "w", encoding="utf-8") as f:
        json.dump(reporte, f, indent=2, ensure_ascii=False)
    logger.info("Reporte de calidad escrito en %s", ruta_salida)
