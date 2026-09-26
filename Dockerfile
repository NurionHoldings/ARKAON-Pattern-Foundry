FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY . .
RUN python -m pip install --no-cache-dir . \
    && python -c "import uvicorn"

CMD ["sh", "-c", "exec python -m uvicorn apf.api:app --host 0.0.0.0 --port ${PORT:-8000}"]
