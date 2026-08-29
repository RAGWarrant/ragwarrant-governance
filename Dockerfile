ARG PYTHON_BASE=python:3.11-slim@sha256:a630a63cdb314e2d138a2fca3e375e319e8568346ffafac5b980f888630ac4f1

FROM ${PYTHON_BASE} AS builder

WORKDIR /build

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

COPY pyproject.toml README.md LICENSE CITATION.cff ./
COPY src ./src

RUN python -m pip install --upgrade pip build wheel \
    && python -m build --wheel --outdir /wheelhouse

FROM ${PYTHON_BASE} AS runtime

LABEL org.opencontainers.image.title="RAGWarrant Governance" \
      org.opencontainers.image.description="Finite publication-safe RAG policy governance job" \
      org.opencontainers.image.licenses="Apache-2.0" \
      org.opencontainers.image.source="https://github.com/RAGWarrant/ragwarrant-governance"

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    RAGWARRANT_CONTAINER=1 \
    RAGWARRANT_REPO_ROOT=/app \
    RAGWARRANT_INPUT_DIR=/inputs \
    RAGWARRANT_OUTPUT_DIR=/outputs \
    RAGWARRANT_OUTPUT_ROOT=/outputs

COPY requirements-runtime.lock ./
RUN python -m pip install --upgrade pip \
    && python -m pip install --require-hashes -r requirements-runtime.lock

COPY --from=builder /wheelhouse/*.whl /tmp/wheelhouse/
RUN python -m pip install --no-deps /tmp/wheelhouse/*.whl \
    && rm -rf /tmp/wheelhouse

COPY configs ./configs
COPY deploy ./deploy
COPY docker ./docker
COPY schemas ./schemas
COPY .gitattributes .dockerignore Dockerfile docker-compose.yml README.md LICENSE CITATION.cff ./

RUN groupadd --system --gid 10001 ragwarrant \
    && useradd --system --uid 10001 --gid ragwarrant --create-home --home-dir /home/ragwarrant --shell /usr/sbin/nologin ragwarrant \
    && mkdir -p /inputs /outputs \
    && chown -R ragwarrant:ragwarrant /outputs /home/ragwarrant

# The named USER ragwarrant is represented by the fixed numeric UID:GID below.
USER 10001:10001

STOPSIGNAL SIGTERM

ENTRYPOINT ["ragwarrant"]
CMD ["--help"]
