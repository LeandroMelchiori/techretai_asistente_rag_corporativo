# Despliegue en Oracle Cloud Infrastructure (OCI)

Esta guía cubre el requisito del desafío de **publicar el agente en OCI usando
al menos un servicio de Oracle Cloud**. Se propone la ruta más simple y
económica: **OCI Container Registry (OCIR) + Container Instances**, con
**Object Storage** para los documentos originales y **OCI Vault** para las
credenciales.

> No necesitás Kubernetes para aprobar el desafío. Container Instances corre el
> contenedor sin que gestiones ninguna VM.

## Arquitectura

```
   Documentos (PDF/Word/Excel/…)
            │
            ▼
   [ OCI Object Storage ]  ── almacenamiento de los archivos originales
            │
            ▼
   [ Contenedor del agente ]  (imagen en OCIR, corriendo en Container Instances)
      ├─ Ingesta + ChromaDB (base vectorial embebida)
      ├─ RAG + LLM (Gemini / OpenAI)
      └─ Interfaz Streamlit  ──►  puerto 8501 (público vía Load Balancer o IP)
            │
            ▼
   [ OCI Vault ]  ── guarda GOOGLE_API_KEY / OPENAI_API_KEY
```

Servicios de OCI utilizados (con uno alcanza para el desafío; acá usamos varios):

| Servicio | Uso |
|---|---|
| **Container Registry (OCIR)** | Alojar la imagen Docker del agente |
| **Container Instances** | Ejecutar el contenedor sin administrar VMs |
| **Object Storage** | Guardar los documentos originales |
| **Vault** | Guardar las API keys de forma segura |

## Paso 1 — Preparar la imagen

```bash
# Autenticarse contra el Container Registry de tu región (ej. sa-saopaulo-1)
docker login <region-key>.ocir.io -u '<tenancy-namespace>/<usuario>'

# Construir y etiquetar la imagen
docker build -t <region-key>.ocir.io/<tenancy-namespace>/techretail-agente:1.0 .

# Publicarla en OCIR
docker push <region-key>.ocir.io/<tenancy-namespace>/techretail-agente:1.0
```

## Paso 2 — Guardar la API key en OCI Vault

1. En la consola de OCI: **Identity & Security → Vault → Create Vault**.
2. Crear una **Master Encryption Key**.
3. Crear un **Secret** llamado `GOOGLE_API_KEY` (o `OPENAI_API_KEY`) con tu clave.
4. Anotar el OCID del secreto para inyectarlo como variable de entorno.

## Paso 3 — (Opcional) Subir los documentos a Object Storage

```bash
oci os bucket create --name techretail-docs
oci os object bulk-upload --bucket-name techretail-docs --src-dir documentos/
```

Los documentos ya viajan dentro de la imagen, así que este paso es para tener
la fuente original versionada y para el pipeline de actualización.

## Paso 4 — Crear la Container Instance

Consola de OCI: **Developer Services → Container Instances → Create**.

- **Imagen:** la de OCIR del paso 1.
- **Puerto:** `8501` (Streamlit).
- **Variables de entorno:**
  - `LLM_PROVIDER=gemini`
  - `GOOGLE_API_KEY` → referenciando el secreto del Vault.
- **Shape:** 1 OCPU / 4 GB alcanza para el prototipo.

Al crear la instancia se indexan los documentos. Si preferís no indexar en el
build, agregá un arranque que ejecute `python -m scripts.ingest --reset` antes
de levantar Streamlit (por ejemplo, con un pequeño `entrypoint.sh`).

## Paso 5 — Exponer y probar

- Asignar una **IP pública** a la Container Instance o ponerla detrás de un
  **Load Balancer** de OCI.
- Abrir el puerto 8501 en la **Network Security Group** de la VCN.
- Acceder a `http://<ip-publica>:8501` y probar el agente.
- **Sacar una captura o grabar un video** del agente respondiendo en la nube y
  agregarlo al README (es un requisito del desafío).

## Alternativas dentro de OCI

- **Compute (VM):** levantar una instancia, instalar Docker y correr el
  contenedor. Más control, requiere administrar la VM.
- **OKE (Kubernetes):** para escalado automático según el volumen de preguntas.
- **Base vectorial nativa de Oracle:** reemplazar ChromaDB por **Oracle
  Database 23ai / Autonomous Database**, que soporta búsqueda vectorial nativa.
  Suma puntos por profundizar en el ecosistema OCI (ver `src/vectorstore.py`
  para el punto de reemplazo).

## Costos

Container Instances y una VM E2.1.Micro entran en el **Always Free / Free Tier**
de OCI para prototipos. Revisá los límites vigentes de tu cuenta antes de
escalar.
