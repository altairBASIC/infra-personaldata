FROM python:3.12-slim

WORKDIR /app

RUN groupadd -r appuser -g 1000 && \
    useradd -r -u 1000 -g appuser -m appuser && \
    mkdir -p /app/data/input /app/data/silver /app/data/chroma /app/data/metrics && \
    chown -R appuser:appuser /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
