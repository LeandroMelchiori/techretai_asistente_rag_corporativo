#!/usr/bin/env bash
# Despliegue automático de TechRetAI en la VM (lo ejecuta un temporizador de systemd).
#
# Si la imagen :main publicada en GHCR cambió, la despliega fijada por digest y
# espera a que el contenedor quede healthy. Si no lo logra, vuelve a la versión
# anterior y recuerda el digest fallido para no reintentarlo en cada ciclo.
set -euo pipefail

IMAGEN="ghcr.io/leandromelchiori/techretai"
ORIGEN="https://github.com/LeandroMelchiori/techretai_asistente_rag_corporativo"
DIR="/opt/apps/apps/techretai"
RUNTIME_ENV="/etc/docker-platform/apps/techretai/runtime.env"
CONTENEDOR="techretai-app-1"
ESTADO="/var/lib/techretai-autodeploy"

mkdir -p "$ESTADO"
cd "$DIR"
compose() { docker compose --env-file .env --env-file "$RUNTIME_ENV" "$@"; }

docker pull --quiet "$IMAGEN:main" >/dev/null
nueva=$(docker image inspect --format '{{range .RepoDigests}}{{println .}}{{end}}' "$IMAGEN:main" | grep "^$IMAGEN@" | head -n 1)
actual=$(sed -n 's/^TECHRETAI_IMAGE=//p' .env)

if [ -z "$nueva" ] || [ "$nueva" = "$actual" ]; then
  exit 0
fi
if [ "$nueva" = "$(cat "$ESTADO/fallida" 2>/dev/null || true)" ]; then
  exit 0
fi

echo "Desplegando $nueva (antes: $actual)"
sed -i "s|^TECHRETAI_IMAGE=.*|TECHRETAI_IMAGE=$nueva|" .env
compose up -d app

for _ in $(seq 1 24); do
  estado=$(docker inspect --format '{{.State.Health.Status}}' "$CONTENEDOR" 2>/dev/null || echo desconocido)
  if [ "$estado" = "healthy" ]; then
    echo "Desplegado: $nueva"
    rm -f "$ESTADO/fallida"
    # Borra sólo versiones viejas de esta aplicación que ya no usa ningún contenedor.
    docker image prune --force --filter "label=org.opencontainers.image.source=$ORIGEN" >/dev/null
    exit 0
  fi
  sleep 5
done

echo "La versión nueva no quedó healthy: vuelvo a $actual" >&2
echo "$nueva" > "$ESTADO/fallida"
sed -i "s|^TECHRETAI_IMAGE=.*|TECHRETAI_IMAGE=$actual|" .env
compose up -d app
exit 1
