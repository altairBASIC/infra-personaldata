"""Tests del generador de correos sintéticos (generar_datos.py)."""

from __future__ import annotations

from generar_datos import generar_correos


class TestGenerador:
    """Tests del generador de correos sintéticos."""

    def test_genera_correos(self):
        """El generador produce una lista no vacía de correos."""
        correos, info = generar_correos(semilla=42)
        assert len(correos) > 0

    def test_cantidad_en_rango(self):
        """El total de correos está dentro del rango esperado (9-18)."""
        correos, info = generar_correos(semilla=42)
        assert 9 <= len(correos) <= 18

    def test_buenos_en_rango(self):
        """La cantidad de correos buenos está entre 5 y 10."""
        correos, info = generar_correos(semilla=42)
        assert 5 <= info["n_buenos"] <= 10

    def test_malos_en_rango(self):
        """La cantidad de correos malos está entre 4 y 8."""
        correos, info = generar_correos(semilla=42)
        assert 4 <= info["n_malos"] <= 8

    def test_semilla_reproducible(self):
        """Misma semilla produce exactamente los mismos correos."""
        correos_a, info_a = generar_correos(semilla=42)
        correos_b, info_b = generar_correos(semilla=42)
        assert info_a == info_b
        assert len(correos_a) == len(correos_b)

    def test_semillas_distintas_varian(self):
        """Semillas distintas pueden producir resultados distintos."""
        _, info_42 = generar_correos(semilla=42)
        _, info_7 = generar_correos(semilla=7)
        assert (info_42["n_buenos"], info_42["n_malos"]) != (info_7["n_buenos"], info_7["n_malos"]) \
            or info_42["reglas_rotas"] != info_7["reglas_rotas"]

    def test_rompe_reglas_esperadas(self):
        """Las reglas rotas son un subconjunto de las 4 rompibles."""
        correos, info = generar_correos(semilla=42)
        reglas_validas = {"r01", "r02", "r03", "r04"}
        assert set(info["reglas_rotas"].keys()).issubset(reglas_validas)