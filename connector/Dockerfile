FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /build

RUN pip install --no-cache-dir build

COPY pyproject.toml ./
COPY src ./src

RUN python -m build --wheel --outdir /dist

FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY --from=builder /dist/*.whl /tmp/

RUN pip install --no-cache-dir /tmp/*.whl \
    && rm -f /tmp/*.whl \
    && adduser --disabled-password --gecos "" appuser \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8100

CMD ["uvicorn", "testflying_connector.main:app", "--host", "0.0.0.0", "--port", "8100"]
