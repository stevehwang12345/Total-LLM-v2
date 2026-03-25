FROM python:3.11-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY src ./src

RUN pip install --no-cache-dir -e .

EXPOSE 9002

HEALTHCHECK --interval=20s --timeout=5s --retries=5 CMD curl -f http://localhost:9002/health || exit 1

CMD ["uvicorn", "total_llm.app:app", "--host", "0.0.0.0", "--port", "9002"]
