# Use the official Python 3.10 base image
FROM python:3.10

# Install dockerize
ENV DOCKERIZE_VERSION v0.7.0
RUN ARCH= && \
    case "$(uname -m)" in \
    x86_64) ARCH='amd64' ;; \
    arm64) ARCH='arm64' ;; \
    aarch64) ARCH='arm64' ;; \
    *) echo "unsupported architecture"; exit 1 ;; \
    esac && \
    wget https://github.com/jwilder/dockerize/releases/download/$DOCKERIZE_VERSION/dockerize-linux-$ARCH-$DOCKERIZE_VERSION.tar.gz \
    && tar -C /usr/local/bin -xzvf dockerize-linux-$ARCH-$DOCKERIZE_VERSION.tar.gz \
    && rm dockerize-linux-$ARCH-$DOCKERIZE_VERSION.tar.gz

ENV PATH="/usr/local/bin:${PATH}"

# Set the working directory in the container
WORKDIR /usr/src/app

# Install Poetry
RUN pip install --upgrade pip && \
    pip install poetry

# Copy the pyproject.toml (and optionally poetry.lock) to /usr/src/app
COPY pyproject.toml poetry.lock* /usr/src/app/

# Install project dependencies with Poetry
# Note: Configuring Poetry to not create a virtual environment inside the Docker container
RUN poetry config virtualenvs.create false && \
    poetry install --no-dev --no-root

# Copy the application source code into the container
COPY src ./src
COPY *.py ./

# Create a non-root user (uncomment if needed)
# RUN useradd -m indexer
# USER indexer

# Command to run the application
CMD ["dockerize", "-wait", "tcp://db:3306", "-timeout", "180s", "python3.10", "start.py"]