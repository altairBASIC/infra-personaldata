"""Tests de la etapa Silver -> Gold: tablas, linaje y reporte de calidad."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import duckdb
import polars as pl
import pytest

from generar_datos import generar_correos, escribir_mbox
from pipeline.etapas.normaliza import normalizar_mbox_desde_archivo
from pipeline.etapas.calidad import aplica_todas


@pytest.fixture
def silver_de_prueba(tmp_path):
    """Genera correos, los normaliza y los guarda como Silver de prueba.

    Devuelve la carpeta donde quedó el Parquet de Silver.
    """
    correos, _ = generar_correos(semilla=42)
    mbox_path = tmp_path / "correos.mbox"
    escribir_mbox(correos, str(mbox_path))

    df = normalizar_mbox_desde_archivo(mbox_path, str(uuid4()))
    df_ok, _ = aplica_todas(df)

    silver_dir = tmp_path / "silver"
    silver_dir.mkdir()
    df_ok.write_parquet(silver_dir / "datos.parquet")

    return silver_dir


def _correr_gold(silver_dir, tmp_path, monkeypatch, run_id="test-run"):
    """Helper: corre Gold apuntando a carpetas temporales.

    Devuelve (carpeta_gold, ruta_reporte, ruta_linaje).
    """
    gold_dir = tmp_path / "gold"
    reporte_path = tmp_path / "metrics" / "reporte_gold.json"
    linaje_path = tmp_path / "linaje.json"

    monkeypatch.setenv("SILVER_PATH", str(silver_dir))
    monkeypatch.setenv("GOLD_PATH", str(gold_dir))
    monkeypatch.setenv("LINAJE_PATH", str(linaje_path))
    monkeypatch.setenv("METRICS_PATH", str(tmp_path / "metrics"))

    from pipeline.etapas.gold import ejecutar_gold
    ejecutar_gold(run_id=run_id)
    return gold_dir, reporte_path, linaje_path


class TestGold:
    """Tests de la etapa Silver -> Gold (las 5 tablas)."""

    def test_genera_cinco_tablas(self, silver_de_prueba, tmp_path, monkeypatch):
        """Gold debe generar exactamente 5 tablas Parquet."""
        gold_dir, _, _ = _correr_gold(silver_de_prueba, tmp_path, monkeypatch)
        parquets = list(gold_dir.glob("*.parquet"))
        assert len(parquets) == 5

    def test_tablas_esperadas_existen(self, silver_de_prueba, tmp_path, monkeypatch):
        """Las 5 tablas tienen los nombres esperados."""
        gold_dir, _, _ = _correr_gold(silver_de_prueba, tmp_path, monkeypatch)
        nombres = {p.stem for p in gold_dir.glob("*.parquet")}
        esperadas = {
            "actividad_por_actor", "volumen_por_mes", "distribucion_por_canal",
            "recencia_por_actor", "resumen_general",
        }
        assert nombres == esperadas

    def test_actividad_tiene_columnas_correctas(self, silver_de_prueba, tmp_path, monkeypatch):
        """La tabla actividad_por_actor tiene las columnas esperadas."""
        gold_dir, _, _ = _correr_gold(silver_de_prueba, tmp_path, monkeypatch)
        con = duckdb.connect(":memory:")
        df = con.execute(
            f"SELECT * FROM read_parquet('{gold_dir / 'actividad_por_actor.parquet'}')"
        ).pl()
        con.close()
        assert df.columns == ["actor", "total_correos"]

    def test_ninguna_tabla_vacia(self, silver_de_prueba, tmp_path, monkeypatch):
        """Con datos válidos, ninguna tabla debe salir vacía."""
        gold_dir, _, _ = _correr_gold(silver_de_prueba, tmp_path, monkeypatch)
        con = duckdb.connect(":memory:")
        for parquet in gold_dir.glob("*.parquet"):
            filas = con.execute(f"SELECT COUNT(*) FROM read_parquet('{parquet}')").fetchone()[0]
            assert filas > 0, f"La tabla {parquet.stem} salió vacía"
        con.close()

    def test_coherencia_contactos(self, silver_de_prueba, tmp_path, monkeypatch):
        """El total de contactos del resumen cuadra con la tabla de actores."""
        gold_dir, _, _ = _correr_gold(silver_de_prueba, tmp_path, monkeypatch)
        con = duckdb.connect(":memory:")
        contactos_resumen = con.execute(
            f"SELECT total_contactos FROM read_parquet('{gold_dir / 'resumen_general.parquet'}')"
        ).fetchone()[0]
        filas_actores = con.execute(
            f"SELECT COUNT(*) FROM read_parquet('{gold_dir / 'actividad_por_actor.parquet'}')"
        ).fetchone()[0]
        con.close()
        assert contactos_resumen == filas_actores


class TestLinaje:
    """Tests de que Gold registra el linaje correctamente."""

    def test_linaje_se_crea(self, silver_de_prueba, tmp_path, monkeypatch):
        """Gold debe crear el archivo linaje.json."""
        _, _, linaje_path = _correr_gold(silver_de_prueba, tmp_path, monkeypatch)
        assert linaje_path.exists()

    def test_linaje_tiene_cinco_etapas(self, silver_de_prueba, tmp_path, monkeypatch):
        """El linaje debe tener una entrada por cada tabla (opción B = 5)."""
        _, _, linaje_path = _correr_gold(silver_de_prueba, tmp_path, monkeypatch)
        linaje = json.loads(linaje_path.read_text())
        assert len(linaje["etapas"]) == 5

    def test_etapas_tienen_campos_correctos(self, silver_de_prueba, tmp_path, monkeypatch):
        """Cada etapa del linaje tiene los campos esperados."""
        _, _, linaje_path = _correr_gold(silver_de_prueba, tmp_path, monkeypatch)
        linaje = json.loads(linaje_path.read_text())
        for etapa in linaje["etapas"]:
            assert "etapa" in etapa
            assert "filas_leidas" in etapa
            assert "filas_escritas" in etapa
            assert "duracion_s" in etapa

    def test_nombres_etapas_tienen_prefijo_gold(self, silver_de_prueba, tmp_path, monkeypatch):
        """Las etapas registradas empiezan con 'gold_'."""
        _, _, linaje_path = _correr_gold(silver_de_prueba, tmp_path, monkeypatch)
        linaje = json.loads(linaje_path.read_text())
        for etapa in linaje["etapas"]:
            assert etapa["etapa"].startswith("gold_")

    def test_run_id_se_respeta(self, silver_de_prueba, tmp_path, monkeypatch):
        """El run_id que se le pasa a Gold aparece en el linaje."""
        _, _, linaje_path = _correr_gold(silver_de_prueba, tmp_path, monkeypatch, run_id="mi-run-456")
        linaje = json.loads(linaje_path.read_text())
        assert linaje["ingest_run_id"] == "mi-run-456"


class TestReporteCalidad:
    """Tests del reporte de calidad de Gold."""

    def test_reporte_se_genera(self, silver_de_prueba, tmp_path, monkeypatch):
        """El reporte de calidad se escribe a disco."""
        _, reporte_path, _ = _correr_gold(silver_de_prueba, tmp_path, monkeypatch)
        assert reporte_path.exists()

    def test_veredicto_todo_ok_con_datos_sanos(self, silver_de_prueba, tmp_path, monkeypatch):
        """Con datos válidos, el veredicto debe ser 'todo_ok'."""
        _, reporte_path, _ = _correr_gold(silver_de_prueba, tmp_path, monkeypatch)
        reporte = json.loads(reporte_path.read_text())
        assert reporte["veredicto"] == "todo_ok"

    def test_no_hay_tablas_vacias_con_datos_sanos(self, silver_de_prueba, tmp_path, monkeypatch):
        """Con datos válidos, la lista de tablas vacías debe estar vacía."""
        _, reporte_path, _ = _correr_gold(silver_de_prueba, tmp_path, monkeypatch)
        reporte = json.loads(reporte_path.read_text())
        assert reporte["tablas_vacias"] == []

    def test_detecta_tabla_vacia(self, silver_de_prueba, tmp_path, monkeypatch):
        """Si una tabla sale vacía, el reporte la detecta y marca problemas."""
        from pipeline.etapas.gold import escribir_reporte_calidad

        gold_dir, _, _ = _correr_gold(silver_de_prueba, tmp_path, monkeypatch)

        # Forzamos un problema: reemplazamos actividad_por_actor por una VACÍA
        pl.DataFrame({"actor": [], "total_correos": []}).write_parquet(
            gold_dir / "actividad_por_actor.parquet"
        )

        con = duckdb.connect(":memory:")
        nombres = ["actividad_por_actor", "volumen_por_mes", "distribucion_por_canal",
                   "recencia_por_actor", "resumen_general"]
        reporte = escribir_reporte_calidad(con, nombres)
        con.close()

        assert "actividad_por_actor" in reporte["tablas_vacias"]
        assert reporte["veredicto"] == "hay_problemas"