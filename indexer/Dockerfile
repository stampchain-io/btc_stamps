# Build stage
ARG PYTHON_VERSION=3.12
ARG INSTALL_DEV=false
FROM python:${PYTHON_VERSION}-slim AS builder

# Build arguments
ARG POETRY_VERSION=1.8.2
ARG TARGETARCH
ARG INSTALL_DEV

# Environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_VERSION=${POETRY_VERSION} \
    POETRY_HOME="/opt/poetry" \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    wget \
    libgmp-dev \
    libmpfr-dev \
    libmpc-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Rust
RUN curl https://sh.rustup.rs -sSf | sh -s -- -y && \
    export PATH="$HOME/.cargo/bin:$PATH" && \
    rustc --version && cargo --version

# Install Poetry and Maturin
RUN pip install --no-cache-dir "poetry==${POETRY_VERSION}" "maturin==1.4.0"

WORKDIR /app

# Copy all source early (to support pyproject-defined packages)
COPY . .

# Install all dependencies, including the app itself (for entrypoints to work)
RUN if [ "$INSTALL_DEV" = "true" ]; then \
      poetry install --with dev; \
    else \
      poetry install --without dev; \
    fi

# Build the Rust extension and output it to target/wheels
RUN export PATH="$HOME/.cargo/bin:$PATH" && \
    poetry run maturin build --release --out target/wheels

# Confirm the wheel exists
RUN ls -l target/wheels/

# Install the built Rust extension
RUN pip install target/wheels/*.whl

# Runtime stage
FROM python:${PYTHON_VERSION}-slim

ARG POETRY_VERSION=1.8.2

ENV PYTHONPATH=/app:/app/src \
    POETRY_VERSION=${POETRY_VERSION} \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_HOME="/opt/poetry" \
    POETRY_NO_INTERACTION=1

WORKDIR /app

# Install system/runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    libmagic1 \
    default-libmysqlclient-dev \
    default-mysql-client \
    libgmp-dev \
    libmpfr-dev \
    libmpc-dev \
    libssl-dev \
    netcat-traditional \
    && rm -rf /var/lib/apt/lists/*

# Install dockerize (optional)
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

# Create the non-root user and own app dir
RUN useradd -m indexer && \
    mkdir -p /app && \
    chown -R indexer:indexer /app

# Copy installed Python dependencies from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages

# ✅ Copy installed CLI tools and entry points (like `indexer`)
COPY --from=builder /usr/local/bin/ /usr/local/bin/

# Copy poetry itself
COPY --from=builder /usr/local/bin/poetry /usr/local/bin/poetry

# Copy application code
COPY --from=builder --chown=indexer:indexer /app /app

# Copy entrypoint
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chown indexer:indexer /docker-entrypoint.sh && chmod +x /docker-entrypoint.sh

# Switch to indexer user
USER indexer

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["poetry", "run", "indexer"]

