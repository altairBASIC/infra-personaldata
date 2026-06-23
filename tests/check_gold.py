"""Analiza la discrepancia de coherencia en Gold."""

import duckdb
import polars as pl

silver = "data/test_silver/**/*.parquet"

con = duckdb.connect(":memory:")

print("=== CANALES EN SILVER ===")
rows = con.execute(
    f"SELECT channel, COUNT(*) as n FROM read_parquet('{silver}') GROUP BY channel ORDER BY n DESC"
).fetchall()
for r in rows:
    print(f"  {repr(r[0])}: {r[1]}")

distinct = con.execute(
    f"SELECT COUNT(DISTINCT channel) FROM read_parquet('{silver}')"
).fetchone()[0]
print(f"\nCOUNT(DISTINCT channel) = {distinct}")
print("(SQL estándar: COUNT(DISTINCT) excluye NULLs)")

groups = con.execute(
    f"SELECT COUNT(*) FROM (SELECT channel FROM read_parquet('{silver}') GROUP BY channel)"
).fetchone()[0]
print(f"Grupos GROUP BY channel = {groups}")
print("(GROUP BY incluye NULL como un grupo separado)")

print(f"\n=== DIAGNÓSTICO ===")
print(f"resumen_general.total_canales = {distinct} (usa COUNT DISTINCT → excluye NULL)")
print(f"distribucion_por_canal filas  = {groups} (usa GROUP BY → incluye NULL)")
print(f"Coherencia falla porque compara {distinct} vs {groups}")
print(f"Es un bug en gold.py: debería usar la misma semántica para ambos")

con.close()
