"""Ejecuta el pipeline completo sin MinIO para pruebas locales."""

import json
import os
import shutil
from pathlib import Path

os.environ["MBOX_PATH"] = "data/input/correos_test.mbox"
os.environ["SILVER_PATH"] = "data/test_silver"
os.environ["GOLD_PATH"] = "data/test_gold"
os.environ["CHROMA_PATH"] = "data/test_chroma"
os.environ["METRICS_PATH"] = "data/test_metrics"
os.environ["LINAJE_PATH"] = "data/test_linaje.json"
os.environ["LOG_LEVEL"] = "INFO"

for d in ["data/test_silver", "data/test_gold", "data/test_chroma",
          "data/test_metrics"]:
    if Path(d).exists():
        shutil.rmtree(d)

from pipeline.main import ejecutar_pipeline

print("=" * 60)
print("EJECUTANDO PIPELINE COMPLETO")
print("=" * 60)

resultado = ejecutar_pipeline(
    ruta_mbox=Path("data/input/correos_test.mbox"),
    silver_base=Path("data/test_silver"),
    chroma_path=Path("data/test_chroma"),
    metrics_path=Path("data/test_metrics"),
    linaje_path=Path("data/test_linaje.json"),
    usar_minio=False,
)

print("\n" + "=" * 60)
print("LINAJE")
print("=" * 60)
print(json.dumps(resultado, indent=2, ensure_ascii=False, default=str))

print("\n" + "=" * 60)
print("REPORTE DE CALIDAD (Silver)")
print("=" * 60)
reporte_path = Path("data/test_metrics/reporte_calidad.json")
if reporte_path.exists():
    with open(reporte_path) as f:
        print(json.dumps(json.load(f), indent=2, ensure_ascii=False))

print("\n" + "=" * 60)
print("REPORTE DE CALIDAD (Gold)")
print("=" * 60)
gold_report = Path("data/test_metrics/reporte_gold.json")
if gold_report.exists():
    with open(gold_report) as f:
        print(json.dumps(json.load(f), indent=2, ensure_ascii=False))
else:
    print("No se encontró reporte Gold")

print("\n" + "=" * 60)
print("ARCHIVOS GENERADOS")
print("=" * 60)
for base in ["data/test_silver", "data/test_gold", "data/test_chroma",
             "data/test_metrics"]:
    p = Path(base)
    if p.exists():
        for f in sorted(p.rglob("*")):
            if f.is_file():
                print(f"  {f}  ({f.stat().st_size:,} bytes)")

print("\n" + "=" * 60)
print("VERIFICACIONES")
print("=" * 60)

import polars as pl

silver_files = list(Path("data/test_silver").rglob("*.parquet"))
print(f"\n1. Archivos Silver Parquet: {len(silver_files)}")
for sf in silver_files:
    df = pl.read_parquet(sf)
    print(f"   {sf}: {len(df)} filas, columnas={df.columns}")

if silver_files:
    df_all = pl.read_parquet(Path("data/test_silver") / "**" / "*.parquet")
    print(f"\n2. Total filas Silver: {len(df_all)}")
    print(f"   Actores únicos: {df_all['actor'].n_unique()}")
    print(f"   Sources: {df_all['source'].unique().to_list()}")
    print(f"   Rango fechas: {df_all['timestamp'].min()} → {df_all['timestamp'].max()}")

gold_files = list(Path("data/test_gold").rglob("*.parquet"))
print(f"\n3. Archivos Gold Parquet: {len(gold_files)}")
for gf in gold_files:
    df = pl.read_parquet(gf)
    print(f"   {gf.name}: {len(df)} filas")
    if len(df) <= 15:
        print(df)

import chromadb
client = chromadb.PersistentClient(path="data/test_chroma")
cols = client.list_collections()
print(f"\n4. Colecciones Chroma: {len(cols)}")
for c in cols:
    col = client.get_collection(c.name)
    print(f"   {c.name}: {col.count()} documentos")

print("\n5. Verificación de reglas descartadas:")
with open(reporte_path) as f:
    rep = json.load(f)
print(f"   Total entrada: {rep['total_entrada']}")
print(f"   Total válidas: {rep['total_validas']}")
print(f"   Descartadas: {rep['total_entrada'] - rep['total_validas']}")
for regla, count in rep.get("descartadas_por_regla", {}).items():
    print(f"   - {regla}: {count}")

esperadas_validas = 34
desc = rep["total_entrada"] - rep["total_validas"]
print(f"\n   Esperábamos ~32 válidas de 42, obtuvimos {rep['total_validas']}")
if rep["total_validas"] < 25 or rep["total_validas"] > 40:
    print("   *** ALERTA: número de válidas fuera del rango esperado ***")
else:
    print("   OK: dentro del rango razonable")

print("\n" + "=" * 60)
print("PIPELINE COMPLETADO EXITOSAMENTE")
print("=" * 60)
