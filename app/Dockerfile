# Utilizar la imagen oficial de Deno
FROM denoland/deno:alpine


WORKDIR /app


COPY . .


EXPOSE 8000

RUN deno upgrade
RUN deno run -A dev.ts build
CMD ["deno", "run", "--allow-net", "--allow-read", "--allow-run", "--allow-write", "--allow-env", "main.ts"]
