# Usa una imagen base oficial de Python 3.9
FROM python:3.9.8

#Instala dockerize
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

# Establece el directorio de trabajo en el contenedor
WORKDIR /usr/src/app

# Instala las dependencias de Python
COPY requirements.txt ./
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Copia el código fuente de la aplicación en el contenedor
COPY . .

# Comando para ejecutar la aplicación
CMD ["dockerize", "-wait", "tcp://db:3306", "-timeout", "1m", "python3.9", "start.py"]