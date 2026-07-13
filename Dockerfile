FROM python:3.12-slim

WORKDIR /app

RUN groupadd -r appuser -g 1000 && \
    useradd -r -u 1000 -g appuser -m appuser && \
    mkdir -p /app/data/input /app/data/silver /app/data/gold /app/data/chroma \
             /app/data/metrics && \
    chown -R appuser:appuser /app

# Caché de modelos de HuggingFace fuera de /app/data para que ningún
# volumen de compose la tape en runtime.
ENV HF_HOME=/opt/hf-cache \
    SENTENCE_TRANSFORMERS_HOME=/opt/hf-cache

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# El modelo de embeddings se descarga DURANTE el build y queda horneado en
# la imagen: el build necesita red, el runtime no.
ARG EMBEDDING_MODEL=paraphrase-multilingual-MiniLM-L12-v2
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('${EMBEDDING_MODEL}', device='cpu')" && \
    chown -R appuser:appuser /opt/hf-cache

# Runtime 100% offline: prohibido consultar huggingface.co.
ENV HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

COPY . .
RUN chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
