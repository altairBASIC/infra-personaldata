"""Carga y validación del catálogo de datos con Pydantic."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, field_validator, model_validator

from pipeline.utils.logging_cfg import get_logger

logger = get_logger("catalogo")

_CATALOGO_DEFAULT = Path(__file__).resolve().parent.parent.parent / "catalogo.yaml"


class CatalogoInvalidoError(Exception):
    """El catálogo YAML tiene campos faltantes u obligatorios mal declarados."""


class CampoSchema(BaseModel):
    """Esquema de un campo individual del catálogo."""

    nombre: str
    tipo: str
    obligatorio: bool
    regla: str | None = None
    valor_fijo: str | None = None


class FuenteSchema(BaseModel):
    """Esquema de una fuente de datos en el catálogo."""

    formato: str
    bronze_path: str
    silver_path: str
    campos: list[CampoSchema]
    sensibilidad: str

    @field_validator("campos")
    @classmethod
    def al_menos_un_campo(cls, v: list[CampoSchema]) -> list[CampoSchema]:
        if not v:
            raise ValueError("La fuente debe tener al menos un campo")
        return v

    def campos_obligatorios(self) -> list[CampoSchema]:
        """Retorna solo los campos marcados como obligatorios."""
        return [c for c in self.campos if c.obligatorio]

    def nombres_campos(self) -> list[str]:
        """Retorna la lista de nombres de todos los campos."""
        return [c.nombre for c in self.campos]


class CatalogoSchema(BaseModel):
    """Esquema raíz del catálogo de datos."""

    version: str
    project: str
    fuentes: dict[str, FuenteSchema]

    @field_validator("version")
    @classmethod
    def version_presente(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("La versión del catálogo no puede estar vacía")
        return v

    @model_validator(mode="after")
    def validar_campos_obligatorios_minimos(self) -> "CatalogoSchema":
        """Verifica que cada fuente tenga los campos obligatorios del esquema unificado."""
        campos_requeridos = {"signal_id", "timestamp", "source", "actor", "content_text", "raw_id", "ingest_run_id"}
        for nombre_fuente, fuente in self.fuentes.items():
            nombres = set(fuente.nombres_campos())
            faltantes = campos_requeridos - nombres
            if faltantes:
                raise ValueError(
                    f"Fuente '{nombre_fuente}' no declara campos obligatorios: {faltantes}"
                )
        return self


def cargar_catalogo(ruta: Path | None = None) -> CatalogoSchema:
    """Carga y valida el catálogo desde un archivo YAML.

    Args:
        ruta: Ruta al archivo YAML. Si es ``None``, usa la ruta por defecto.

    Returns:
        Catálogo validado.

    Raises:
        CatalogoInvalidoError: Si el YAML tiene campos faltantes o mal declarados.
        FileNotFoundError: Si el archivo no existe.
    """
    ruta = ruta or _CATALOGO_DEFAULT
    if not ruta.exists():
        raise FileNotFoundError(f"Catálogo no encontrado: {ruta}")

    with open(ruta, encoding="utf-8") as f:
        raw: dict[str, Any] = yaml.safe_load(f)

    if raw is None:
        raise CatalogoInvalidoError("El archivo de catálogo está vacío")

    try:
        catalogo = CatalogoSchema.model_validate(raw)
    except Exception as exc:
        raise CatalogoInvalidoError(f"Catálogo inválido: {exc}") from exc

    logger.info(
        "Catálogo v%s cargado: %d fuentes",
        catalogo.version,
        len(catalogo.fuentes),
    )
    return catalogo


def obtener_fuente(nombre: str, ruta: Path | None = None) -> FuenteSchema:
    """Atajo para obtener una fuente específica del catálogo.

    Args:
        nombre: Nombre de la fuente (e.g. ``mail``).
        ruta: Ruta al catálogo YAML.

    Returns:
        Esquema de la fuente solicitada.

    Raises:
        CatalogoInvalidoError: Si la fuente no existe en el catálogo.
    """
    catalogo = cargar_catalogo(ruta)
    if nombre not in catalogo.fuentes:
        raise CatalogoInvalidoError(f"Fuente '{nombre}' no existe en el catálogo")
    return catalogo.fuentes[nombre]
