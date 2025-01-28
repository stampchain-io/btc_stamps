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

# Install Poetry and Maturin
RUN pip install --no-cache-dir "poetry==${POETRY_VERSION}" "maturin==1.4.0"

WORKDIR /app

# Copy project files
COPY pyproject.toml poetry.lock ./

# Install dependencies
RUN if [ "$INSTALL_DEV" = "true" ]; then \
      poetry install --with dev --no-root; \
    else \
      poetry install --without dev --no-root; \
    fi

# Copy project files (will respect .dockerignore)
COPY . .

# Build Rust parser
RUN poetry run maturin develop --release

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

# Install system dependencies first (as root)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        wget \
        libmagic1 \
        default-libmysqlclient-dev \
        default-mysql-client \
        libgmp-dev \
        libmpfr-dev \
        libmpc-dev \
        netcat-traditional \
        supervisor \
    && rm -rf /var/lib/apt/lists/*

# Install dockerize (as root)
ARG TARGETARCH
ENV ARCH=${TARGETARCH:-amd64} \
    DOCKERIZE_VERSION=v0.7.0

RUN case "${ARCH}" in \
        "amd64")  DOCKERIZE_ARCH=amd64  ;; \
        "arm64")  DOCKERIZE_ARCH=arm64  ;; \
        "arm")    DOCKERIZE_ARCH=armhf  ;; \
        *)        echo "Unsupported architecture: ${ARCH}" && exit 1  ;; \
    esac && \
    wget "https://github.com/jwilder/dockerize/releases/download/$DOCKERIZE_VERSION/dockerize-linux-${DOCKERIZE_ARCH}-$DOCKERIZE_VERSION.tar.gz" && \
    tar -C /usr/local/bin -xzvf "dockerize-linux-${DOCKERIZE_ARCH}-$DOCKERIZE_VERSION.tar.gz" && \
    rm "dockerize-linux-${DOCKERIZE_ARCH}-$DOCKERIZE_VERSION.tar.gz"

# Create user and set up directories (as root)
RUN useradd -m indexer && \
    mkdir -p /app && \
    chown -R indexer:indexer /app

# Copy Python packages from builder and fix permissions (as root)
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
RUN chown -R indexer:indexer /usr/local/lib/python3.12/site-packages

# Copy Poetry binary (as root)
COPY --from=builder /usr/local/bin/poetry /usr/local/bin/poetry

# Copy application files and set permissions (as root)
COPY --from=builder --chown=indexer:indexer /app /app

# Copy and set up entrypoint script (as root)
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chown indexer:indexer /docker-entrypoint.sh && \
    chmod +x /docker-entrypoint.sh

# Copy supervisor config
COPY supervisor.conf /etc/supervisor/conf.d/indexer.conf

# Switch to indexer user after all system operations are complete
USER indexer

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/indexer.conf"]