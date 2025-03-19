# Build stage
ARG PYTHON_VERSION=3.12
ARG INSTALL_DEV=false
FROM python:${PYTHON_VERSION}-alpine AS builder

# Build arguments
ARG POETRY_VERSION=2.1.1
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
RUN apk add --no-cache \
    build-base \
    gcc \
    g++ \
    libffi-dev \
    openssl-dev \
    git \
    libc-dev \
    musl-dev \
    mariadb-dev \
    curl \
    gmp-dev \
    mpfr-dev \
    mpc1-dev \
    file \
    linux-headers \
    patchelf

# Install Rust toolchain
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

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

# Build Rust parser (using maturin directly instead of the script)
RUN cd src/rust_parser && \
    cargo fmt -- --check && \
    cargo clippy -- -D warnings && \
    maturin build --release && \
    pip install target/wheels/*.whl

# Install project with all dependencies
RUN if [ "$INSTALL_DEV" = "true" ]; then \
      poetry install --with dev; \
    else \
      poetry install --without dev; \
    fi

# Runtime stage
FROM python:${PYTHON_VERSION}-alpine

# Build arguments for runtime
ARG POETRY_VERSION=2.1.1

ENV PYTHONPATH=/app:/app/src \
    POETRY_VERSION=${POETRY_VERSION} \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_HOME="/opt/poetry" \
    POETRY_NO_INTERACTION=1

WORKDIR /app

# Install system dependencies first (as root)
RUN apk add --no-cache \
    libpq \
    mariadb-connector-c \
    wget \
    bash \
    tzdata \
    file \
    mysql-client \
    gmp-dev \
    mpfr-dev \
    mpc1-dev \
    netcat-openbsd \
    supervisor && \
    mkdir -p /etc/supervisor/conf.d /var/log /var/run

# Create user and set up directories (as root)
RUN adduser -D -h /home/indexer indexer && \
    mkdir -p /app && \
    chown -R indexer:indexer /app

# Copy Python packages from builder and fix permissions (as root)
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
RUN chown -R indexer:indexer /usr/local/lib/python3.12/site-packages

# Copy Poetry binary (as root)
COPY --from=builder /usr/local/bin/poetry /usr/local/bin/poetry

# Copy application files and set permissions (as root)
COPY --from=builder --chown=indexer:indexer /app /app

# Copy and set up entrypoint and wait scripts (as root)
COPY docker-entrypoint.sh /docker-entrypoint.sh
COPY wait-for-mysql.sh /app/wait-for-mysql.sh
RUN chown indexer:indexer /docker-entrypoint.sh /app/wait-for-mysql.sh && \
    chmod +x /docker-entrypoint.sh /app/wait-for-mysql.sh

# Copy supervisor config
COPY supervisor.conf /etc/supervisor/conf.d/indexer.conf

# Switch to indexer user after all system operations are complete
USER indexer

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/indexer.conf"]