# Imagen del agente RAG corporativo (TechRetAI).
# Pensada para la plataforma Docker + Traefik de OCI: usuario sin privilegios,
# root filesystem de solo lectura y datos persistentes en el volumen /data.
FROM python:3.11-slim

# Evita prompts y bytecode; salida sin buffer para ver logs en tiempo real.
# HOME apunta a /tmp (tmpfs) porque el resto del filesystem es de solo lectura.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/tmp \
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    ANONYMIZED_TELEMETRY=False \
    CHROMA_DIR=/data/chroma \
    LOG_FILE=/data/logs/consultas.jsonl

WORKDIR /app

# Dependencias primero (mejor cacheo de capas).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Código y perfiles de empresa. Los documentos quedan fuera (.dockerignore):
# la imagen es pública y no debe llevar información de ninguna empresa.
COPY . .

# Versión publicada en /app/static/version.txt: el pipeline la consulta para
# confirmar que el despliegue llegó a producción.
ARG GIT_SHA=local
RUN mkdir -p app/static && printf '%s\n' "$GIT_SHA" > app/static/version.txt

# Usuario con UID fijo y /data con su dueño: el volumen nombrado hereda estos
# permisos la primera vez que se monta.
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin techretai \
    && mkdir -p /data/chroma /data/logs \
    && chown -R 10001:10001 /data
USER 10001:10001

# El índice no se genera en el build (necesitaría la API key dentro de la
# imagen): se crea una vez en el volumen con el servicio "ingest" del Compose.

EXPOSE 8501

HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=4)" || exit 1

CMD ["streamlit", "run", "app/streamlit_app.py"]
