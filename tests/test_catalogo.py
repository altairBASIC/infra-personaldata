"""Tests para la carga y validación del catálogo de datos."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from pipeline.metadata.catalogo import (
    CatalogoInvalidoError,
    CatalogoSchema,
    cargar_catalogo,
    obtener_fuente,
)

CATALOGO_REAL = Path(__file__).resolve().parent.parent / "catalogo.yaml"


class TestCargarCatalogo:
    """Tests de carga del catálogo real."""

    def test_carga_exitosa(self) -> None:
        catalogo = cargar_catalogo(CATALOGO_REAL)
        assert catalogo.version == "1.0"
        assert catalogo.project == "infra-datos-personal"
        assert "mail" in catalogo.fuentes

    def test_version_presente(self) -> None:
        catalogo = cargar_catalogo(CATALOGO_REAL)
        assert catalogo.version
        assert len(catalogo.version.strip()) > 0

    def test_todos_los_campos_obligatorios(self) -> None:
        catalogo = cargar_catalogo(CATALOGO_REAL)
        mail = catalogo.fuentes["mail"]
        nombres = mail.nombres_campos()
        for campo_req in ["signal_id", "timestamp", "source", "actor",
                          "content_text", "raw_id", "ingest_run_id"]:
            assert campo_req in nombres, f"Campo obligatorio faltante: {campo_req}"

    def test_campos_obligatorios_marcados(self) -> None:
        catalogo = cargar_catalogo(CATALOGO_REAL)
        mail = catalogo.fuentes["mail"]
        obligatorios = {c.nombre for c in mail.campos_obligatorios()}
        for campo in ["signal_id", "timestamp", "source", "actor",
                       "content_text", "raw_id", "ingest_run_id"]:
            assert campo in obligatorios

    def test_fuente_mail_formato_mbox(self) -> None:
        catalogo = cargar_catalogo(CATALOGO_REAL)
        assert catalogo.fuentes["mail"].formato == "mbox"

    def test_sensibilidad_alta(self) -> None:
        catalogo = cargar_catalogo(CATALOGO_REAL)
        assert catalogo.fuentes["mail"].sensibilidad == "alta"


class TestObtenerFuente:
    """Tests para obtener fuentes individuales."""

    def test_fuente_existente(self) -> None:
        fuente = obtener_fuente("mail", CATALOGO_REAL)
        assert fuente.formato == "mbox"

    def test_fuente_inexistente(self) -> None:
        with pytest.raises(CatalogoInvalidoError, match="no existe"):
            obtener_fuente("noexiste", CATALOGO_REAL)


class TestValidacionCatalogo:
    """Tests de validación negativa."""

    def test_archivo_inexistente(self) -> None:
        with pytest.raises(FileNotFoundError):
            cargar_catalogo(Path("/ruta/falsa/catalogo.yaml"))

    def test_yaml_sin_version(self, tmp_path: Path) -> None:
        ruta = tmp_path / "bad.yaml"
        ruta.write_text(yaml.dump({"project": "x", "fuentes": {}}))
        with pytest.raises(CatalogoInvalidoError):
            cargar_catalogo(ruta)

    def test_yaml_vacio(self, tmp_path: Path) -> None:
        ruta = tmp_path / "empty.yaml"
        ruta.write_text("")
        with pytest.raises(CatalogoInvalidoError):
            cargar_catalogo(ruta)

    def test_fuente_sin_campos_obligatorios(self, tmp_path: Path) -> None:
        data = {
            "version": "1.0",
            "project": "test",
            "fuentes": {
                "mail": {
                    "formato": "mbox",
                    "bronze_path": "s3://x",
                    "silver_path": "silver/x",
                    "campos": [
                        {"nombre": "signal_id", "tipo": "string", "obligatorio": True},
                    ],
                    "sensibilidad": "alta",
                }
            },
        }
        ruta = tmp_path / "incomplete.yaml"
        ruta.write_text(yaml.dump(data))
        with pytest.raises(CatalogoInvalidoError):
            cargar_catalogo(ruta)
