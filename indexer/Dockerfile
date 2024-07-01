ARG PYTHON_VERSION=3.12
FROM python:${PYTHON_VERSION}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_VERSION=1.8.2 \
    POETRY_HOME="/opt/poetry" \
    POETRY_NO_INTERACTION=1


# Install dockerize
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

WORKDIR /usr/src/app

RUN useradd -m indexer

# Install Poetry and system dependencies
RUN pip install --upgrade pip && \
    pip install "poetry==${POETRY_VERSION}" && \
    apt-get update && apt-get install -y wget && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

COPY --chown=indexer:indexer pyproject.toml poetry.lock* /usr/src/app/
COPY --chown=indexer:indexer src ./src
COPY --chown=indexer:indexer *.py ./

RUN poetry config virtualenvs.create false && \
    poetry install --only main

USER indexer

# CMD ["sh", "-c", "dockerize -wait tcp://db:3306 -timeout 5m && poetry run indexer"]
CMD ["poetry", "run", "indexer"]