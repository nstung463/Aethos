FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY src ./src
COPY main.py aethos.py ./

RUN pip install --upgrade pip && pip install -e ".[daytona]"

RUN mkdir -p /app/workspace /app/logs

EXPOSE 8080

CMD ["python", "main.py"]
