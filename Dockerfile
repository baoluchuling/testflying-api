FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /build

RUN pip install --no-cache-dir build

COPY pyproject.toml README.md ./
COPY src ./src

RUN python -m build --wheel --outdir /dist

FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY --from=builder /dist/*.whl /tmp/
COPY alembic ./alembic
COPY alembic.ini ./

RUN pip install --no-cache-dir /tmp/*.whl \
    && rm -f /tmp/*.whl \
    && adduser --disabled-password --gecos "" appuser \
    && mkdir -p /app/data \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

CMD ["uvicorn", "testflying_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
