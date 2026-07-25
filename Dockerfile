# Imagen del Agente RAG Corporativo de TechRetail.
# Se construye con la base vectorial ya indexada dentro de la imagen para que
# el contenedor arranque listo para responder.
FROM python:3.11-slim

# Evita prompts y bytecode; salida sin buffer para ver logs en tiempo real.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0

WORKDIR /app

# Dependencias primero (mejor cacheo de capas).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Código y documentos.
COPY . .

# Indexa los documentos en tiempo de build. Requiere la credencial del
# proveedor como build-arg (o se puede indexar al arrancar, ver docs/deploy_oci.md).
# ARG GOOGLE_API_KEY
# ENV GOOGLE_API_KEY=$GOOGLE_API_KEY
# RUN python -m scripts.ingest --reset

EXPOSE 8501

# Chequeo de salud para orquestadores (Container Instances / OKE).
HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')" || exit 1

CMD ["streamlit", "run", "app/streamlit_app.py"]
