# syntax=docker/dockerfile:1
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv

RUN useradd --create-home --uid 10001 chusky \
 && mkdir -p /etc/chusky-bridge/wsdl /etc/chusky-bridge/certs \
 && chown -R chusky /etc/chusky-bridge

COPY pyproject.toml README.md alembic.ini ./
COPY chusky_bridge ./chusky_bridge
COPY migrations ./migrations
COPY connectors_manifests ./connectors_manifests
COPY systems ./systems
RUN pip install . && chown -R chusky /srv

# Optional drivers: build a derived image that installs the vendor client libraries first, then
#   pip install ".[odbc]" ".[sap]" ".[mq]" ".[industrial]" ".[dicom]" ".[redis]" ".[aws]"

USER chusky
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4)" || exit 1

CMD ["uvicorn", "chusky_bridge.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
