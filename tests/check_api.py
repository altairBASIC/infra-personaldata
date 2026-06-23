"""Prueba la API contra los datos generados por el pipeline."""

import asyncio
import os

os.environ["SILVER_PATH"] = "data/test_silver"
os.environ["CHROMA_PATH"] = "data/test_chroma"
os.environ["EMBEDDING_MODEL"] = "paraphrase-multilingual-MiniLM-L12-v2"

from httpx import ASGITransport, AsyncClient
from api.main import app


async def main():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:

        print("=" * 60)
        print("TEST API: GET /health")
        print("=" * 60)
        r = await client.get("/health")
        print(f"  Status: {r.status_code}")
        print(f"  Body: {r.json()}")
        assert r.status_code == 200

        print("\n" + "=" * 60)
        print("TEST API: GET /signals (sin filtros)")
        print("=" * 60)
        r = await client.get("/signals")
        data = r.json()
        print(f"  Status: {r.status_code}")
        print(f"  Total: {data['total']}")
        print(f"  Items retornados: {len(data['items'])}")
        assert r.status_code == 200
        assert data["total"] == 34

        print("\n" + "=" * 60)
        print("TEST API: GET /signals?limit=5")
        print("=" * 60)
        r = await client.get("/signals", params={"limit": 5})
        data = r.json()
        print(f"  Status: {r.status_code}")
        print(f"  Items: {len(data['items'])}")
        assert len(data["items"]) == 5

        print("\n" + "=" * 60)
        print("TEST API: GET /signals?actor=ana.garcia@empresa.cl")
        print("=" * 60)
        r = await client.get("/signals", params={"actor": "ana.garcia@empresa.cl"})
        data = r.json()
        print(f"  Status: {r.status_code}")
        print(f"  Total para ana.garcia: {data['total']}")
        for item in data["items"]:
            print(f"    - {item['actor']}: {item['content_text'][:60]}...")
            assert item["actor"] == "ana.garcia@empresa.cl"

        print("\n" + "=" * 60)
        print("TEST API: GET /signals?source=mail")
        print("=" * 60)
        r = await client.get("/signals", params={"source": "mail"})
        data = r.json()
        print(f"  Status: {r.status_code}")
        print(f"  Total source=mail: {data['total']}")
        assert data["total"] == 34

        print("\n" + "=" * 60)
        print("TEST API: GET /signals con rango de fechas")
        print("=" * 60)
        r = await client.get("/signals", params={
            "from_ts": "2024-07-01T00:00:00Z",
            "to_ts": "2024-08-31T23:59:59Z",
            "limit": 100,
        })
        data = r.json()
        print(f"  Status: {r.status_code}")
        print(f"  Total jul-ago 2024: {data['total']}")
        assert data["total"] > 0

        print("\n" + "=" * 60)
        print("TEST API: GET /signals con offset")
        print("=" * 60)
        r = await client.get("/signals", params={"limit": 10, "offset": 30})
        data = r.json()
        print(f"  Status: {r.status_code}")
        print(f"  Items (offset=30, limit=10): {len(data['items'])}")
        assert len(data["items"]) == 4

        print("\n" + "=" * 60)
        print("TEST API: POST /search (planificación)")
        print("=" * 60)
        r = await client.post("/search", json={
            "query": "reunión planificación proyecto",
            "top_k": 3,
        })
        data = r.json()
        print(f"  Status: {r.status_code}")
        print(f"  Resultados: {len(data['results'])}")
        for res in data["results"]:
            print(f"    score={res['score']:.3f} | {res['content_text'][:70]}...")
        assert r.status_code == 200
        assert len(data["results"]) > 0

        print("\n" + "=" * 60)
        print("TEST API: POST /search (seguridad)")
        print("=" * 60)
        r = await client.post("/search", json={
            "query": "vulnerabilidad seguridad servidor actualización",
            "top_k": 3,
        })
        data = r.json()
        print(f"  Status: {r.status_code}")
        for res in data["results"]:
            print(f"    score={res['score']:.3f} | {res['content_text'][:70]}...")

        print("\n" + "=" * 60)
        print("TEST API: POST /search (factura)")
        print("=" * 60)
        r = await client.post("/search", json={
            "query": "factura hosting pago",
            "top_k": 1,
            "source": "mail",
        })
        data = r.json()
        print(f"  Status: {r.status_code}")
        for res in data["results"]:
            print(f"    score={res['score']:.3f} | {res['content_text'][:70]}...")
        assert "factura" in data["results"][0]["content_text"].lower() or \
               "hosting" in data["results"][0]["content_text"].lower()

        print("\n" + "=" * 60)
        print("TEST API: POST /search query vacío (debe dar 422)")
        print("=" * 60)
        r = await client.post("/search", json={"query": "", "top_k": 1})
        print(f"  Status: {r.status_code}")
        assert r.status_code == 422

        print("\n" + "=" * 60)
        print("TODAS LAS PRUEBAS DE API PASARON")
        print("=" * 60)


asyncio.run(main())
