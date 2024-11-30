# Build stage
ARG PYTHON_VERSION=3.12
ARG INSTALL_DEV=false
FROM python:${PYTHON_VERSION}-slim AS builder

# Build arguments
ARG POETRY_VERSION=1.8.2
ARG TARGETARCH
ARG INSTALL_DEV

# Poetry environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_VERSION=${POETRY_VERSION} \
    POETRY_HOME="/opt/poetry" \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    wget \
    libgmp-dev \
    libmpfr-dev \
    libmpc-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip install --no-cache-dir "poetry==${POETRY_VERSION}"

# Create indexer user and set up directories
RUN useradd -m indexer && \
    mkdir -p /app && \
    chown -R indexer:indexer /app && \
    chown -R indexer:indexer /usr/local

WORKDIR /app

# Switch to indexer user for the remaining operations
USER indexer

# Now we can use --chown since the user exists
COPY --chown=indexer:indexer pyproject.toml poetry.lock ./

# Install dependencies
RUN if [ "$INSTALL_DEV" = "true" ]; then \
      poetry install --with dev --no-root; \
    else \
      poetry install --without dev --no-root; \
    fi

# Copy project files (will respect .dockerignore)
COPY --chown=indexer:indexer . .

# Install project with all dependencies
RUN if [ "$INSTALL_DEV" = "true" ]; then \
      poetry install --with dev; \
    else \
      poetry install --without dev; \
    fi

# Runtime stage
FROM python:${PYTHON_VERSION}-slim

# Build arguments for runtime
ARG POETRY_VERSION=1.8.2

ENV PYTHONPATH=/app:/app/src \
    POETRY_VERSION=${POETRY_VERSION} \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_HOME="/opt/poetry" \
    POETRY_NO_INTERACTION=1

WORKDIR /app

# Create user and set up directories
RUN useradd -m indexer && \
    mkdir -p /app && \
    chown -R indexer:indexer /app

# Install system dependencies first
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        wget \
        libmagic1 \
        default-libmysqlclient-dev \
        default-mysql-client \
        libgmp-dev \
        libmpfr-dev \
        libmpc-dev \
        netcat-traditional && \
    rm -rf /var/lib/apt/lists/*

# Copy Python packages from builder and fix permissions
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
RUN chown -R indexer:indexer /usr/local/lib/python3.12/site-packages

# Copy Poetry binary
COPY --from=builder /usr/local/bin/poetry /usr/local/bin/poetry

# Install dockerize
ARG TARGETARCH
ENV ARCH=${TARGETARCH:-amd64} \
    DOCKERIZE_VERSION=v0.7.0

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        wget && \
    rm -rf /var/lib/apt/lists/* && \
    case "${ARCH}" in \
        "amd64")  DOCKERIZE_ARCH=amd64  ;; \
        "arm64")  DOCKERIZE_ARCH=arm64  ;; \
        "arm")    DOCKERIZE_ARCH=armhf  ;; \
        *)        echo "Unsupported architecture: ${ARCH}" && exit 1  ;; \
    esac && \
    wget "https://github.com/jwilder/dockerize/releases/download/$DOCKERIZE_VERSION/dockerize-linux-${DOCKERIZE_ARCH}-$DOCKERIZE_VERSION.tar.gz" && \
    tar -C /usr/local/bin -xzvf "dockerize-linux-${DOCKERIZE_ARCH}-$DOCKERIZE_VERSION.tar.gz" && \
    rm "dockerize-linux-${DOCKERIZE_ARCH}-$DOCKERIZE_VERSION.tar.gz"

# Copy from builder
COPY --from=builder --chown=indexer:indexer /app /app

# Copy and set up entrypoint script
COPY --chown=indexer:indexer docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

USER indexer

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["python", "-m", "start"]