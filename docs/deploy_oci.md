# Despliegue en Oracle Cloud Infrastructure (OCI)

TechRetAI corre como un contenedor más dentro de la **plataforma Docker +
Traefik** de OCI: una VM Ampere A1 (Always Free) administrada con Terraform en el
repositorio [`infrastructure-as-code`](https://github.com/LeandroMelchiori/infrastructure-as-code)
(`oci/docker-platform`), que aloja varias aplicaciones detrás de un único proxy.

La infraestructura (red, NSG, VM, IP pública reservada, Traefik) no vive en este
repositorio. Acá sólo están la imagen (`Dockerfile`) y el Compose de la
aplicación (`deploy/oci/compose.yaml`).

## Arquitectura

```text
Internet ──► techretai.sachadev.me (DNS A → IP pública reservada de la plataforma)
               │
               ▼
        [ Traefik ]  :80 → redirige a HTTPS sólo para este host
               │     :443 → certificado de Let's Encrypt (HTTP-01)
               ▼  red Docker "proxy"
        [ techretai-app ]  Streamlit :8501, UID 10001, root filesystem read-only
               │
               ├─ volumen techretai-data:/data  (ChromaDB + logs/consultas.jsonl)
               └─ API de Gemini (LLM + embeddings)
```

Controles del contenedor, alineados con el baseline de la plataforma:
`no-new-privileges`, `cap_drop: ALL`, usuario no root, `read_only`, `/tmp` como
tmpfs `noexec`, límites de CPU/memoria, healthcheck y ningún puerto publicado en
el host. La única excepción es el volumen `/data` con escritura, porque ChromaDB
(SQLite) y el registro de auditoría necesitan persistir.

## Archivos en la VM

| Ruta | Contenido |
|---|---|
| `/opt/apps/apps/techretai/compose.yaml` | Copia de `deploy/oci/compose.yaml` |
| `/opt/apps/apps/techretai/.env` | `TECHRETAI_IMAGE`, `GEMINI_CHAT_MODEL`, `GEMINI_EMBED_MODEL` (no son secretos) |
| `/etc/docker-platform/apps/techretai/runtime.env` | `GOOGLE_API_KEY` (root, `0600`) |

Los comandos siguientes se ejecutan desde el equipo del operador, que es la única
IP habilitada para SSH en el NSG de la plataforma.

```bash
VM=opc@<ip-publica-de-la-plataforma>   # terraform output -raw server_public_ip
KEY=~/.ssh/application-platform-dev-access
```

## 1. Registrar la aplicación (una sola vez)

```bash
ssh -i $KEY $VM 'sudo install -d -o root -g root -m 0750 /etc/docker-platform/apps/techretai \
  && install -d -m 0750 /opt/apps/apps/techretai'
scp -i $KEY deploy/oci/compose.yaml $VM:/opt/apps/apps/techretai/compose.yaml
```

Cargar la API key desde una sesión SSH en la VM, sin que pase por archivos
locales ni por el historial de la shell:

```bash
read -rsp 'GOOGLE_API_KEY: ' k; echo
printf 'GOOGLE_API_KEY=%s\n' "$k" | sudo install -o root -g root -m 0600 /dev/stdin \
  /etc/docker-platform/apps/techretai/runtime.env; unset k
```

Usá una API key exclusiva para TechRetAI: la plataforma comparte la VM con otras
aplicaciones y root/Docker pueden inspeccionar las variables de los contenedores.

## 2. Construir la imagen

La VM es ARM64, así que la imagen se construye ahí mismo a partir de un commit:

```bash
SHA=$(git rev-parse --short=7 HEAD)
git archive --format=tar HEAD | ssh -i $KEY $VM "docker build -t techretai:$SHA -"
ssh -i $KEY $VM "sed -i 's/^TECHRETAI_IMAGE=.*/TECHRETAI_IMAGE=techretai:$SHA/' /opt/apps/apps/techretai/.env"
```

El `.env` de la aplicación también fija los modelos de Gemini
(`GEMINI_CHAT_MODEL`, `GEMINI_EMBED_MODEL`).

## 3. Indexar los documentos

Crea la colección de ChromaDB dentro del volumen `techretai-data`. Se repite sólo
cuando cambian los documentos o el modelo de embeddings:

```bash
ssh -i $KEY $VM 'cd /opt/apps/apps/techretai && sudo docker compose \
  --env-file .env --env-file /etc/docker-platform/apps/techretai/runtime.env \
  --profile ops run --rm ingest'
```

## 4. Levantar o actualizar el servicio

```bash
ssh -i $KEY $VM 'cd /opt/apps/apps/techretai && sudo docker compose \
  --env-file .env --env-file /etc/docker-platform/apps/techretai/runtime.env \
  up -d app && docker ps --filter name=techretai'
```

Para actualizar: repetir el paso 2 con el nuevo commit y luego el paso 4. Para
volver atrás, escribir en `.env` el tag anterior y repetir el paso 4.

## 5. DNS y HTTPS

En Cloudflare, los registros `A` de `techretai` y `www.techretai` apuntan a la IP
pública **reservada** de la plataforma, en modo *DNS only*. Traefik obtiene el
certificado de Let's Encrypt la primera vez que recibe tráfico para ese host.

La plataforma debe tener HTTPS habilitado con redirección por aplicación
(`https_enabled = true`, `https_redirect_all = false`), para que las apps sin
dominio puedan seguir sirviéndose por HTTP en la misma VM.

## Límites de uso

La app es pública, así que limita el consumo de la API key:

- **Por cliente:** `RATE_LIMIT_PER_CLIENT` preguntas cada `RATE_LIMIT_WINDOW_MIN`
  minutos (15 cada 10 por defecto). El cliente se identifica por `X-Real-Ip`,
  que Traefik reemplaza con la IP real: un cliente no puede falsificarlo.
- **Global:** `RATE_LIMIT_DAILY` preguntas por día entre todos (300 por defecto).
- **Largo:** `MAX_QUESTION_CHARS` caracteres por pregunta (500 por defecto).

Los contadores viven en memoria y se reinician con el contenedor. Para ajustar
los valores, agregarlos al `.env` de la aplicación y repetir el paso 4.

Como segunda barrera, conviene fijar en Google Cloud una cuota diaria para la
Generative Language API y, si el proyecto tiene facturación, una alerta de
presupuesto.

## Verificación

```bash
curl -I http://techretai.sachadev.me      # 308 → https
curl -I https://techretai.sachadev.me     # 200
ssh -i $KEY $VM 'docker inspect --format "{{.State.Health.Status}}" techretai-app-1'
```

## Costos

La VM, la IP reservada y el tráfico entran en el **Always Free** de OCI mientras
el consumo total del tenancy no supere sus límites (los cupos de Ampere A1 se
comparten entre todas las aplicaciones). El único costo variable es el uso de la
API de Gemini.
