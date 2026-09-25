FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY db ./db
RUN pip install --no-cache-dir .
ENV APF_ENV=production
CMD ["sh", "-c", "exec uvicorn apf.api:app --host 0.0.0.0 --port ${PORT:-8000}"]
