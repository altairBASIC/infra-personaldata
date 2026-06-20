FROM python:3.12-slim

WORKDIR /app

RUN groupadd -r appuser -g 1000 && \
    useradd -r -u 1000 -g appuser -m appuser && \
    mkdir -p /app/data/input /app/data/silver /app/data/gold /app/data/chroma \
             /app/data/metrics /app/data/.cache && \
    chown -R appuser:appuser /app

# Caché de modelos de HuggingFace dentro de /app/data (escribible por appuser).
# Evita el PermissionError al guardar el modelo de embeddings.
ENV HF_HOME=/app/data/.cache \
    TRANSFORMERS_CACHE=/app/data/.cache \
    SENTENCE_TRANSFORMERS_HOME=/app/data/.cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
