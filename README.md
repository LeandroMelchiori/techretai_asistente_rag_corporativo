# 🤖 Agente RAG Corporativo — TechRetail Solutions S.R.L.

> Desafío **Challenge AluraAgente ONE - IA for Tech**
> Agente de inteligencia artificial corporativo, accesible para todos los
> colaboradores, capaz de responder preguntas basándose en los documentos
> internos de la empresa.

Este proyecto implementa un **asistente conversacional con RAG**
(*Retrieval-Augmented Generation*) para la empresa ficticia **TechRetail
Solutions S.R.L.**, una plataforma SaaS de e-commerce para PyMEs y
emprendedores en Argentina. El agente ingiere documentos internos en **8
formatos distintos**, los indexa en una base vectorial y responde preguntas
citando siempre la fuente, sin inventar información.

---

## 📸 Demostración en la nube (OCI)

> _Reemplazá esta sección con la captura o el video del agente ejecutándose en
> Oracle Cloud Infrastructure. Es un requisito del desafío._
>
> ```
> ![Agente ejecutándose en OCI](docs/img/demo_oci.png)
> ```

---

## ✨ Características

- **Multi-formato:** procesa PDF, Word (`.docx`), Excel (`.xlsx`), PowerPoint
  (`.pptx`), Markdown, CSV, JSON y HTML.
- **Multi-dominio:** documentos organizados por área (RH, Financiero, Legal,
  Operacional, Comercial, Estratégico, Datos y Sistemas).
- **RAG completo:** extracción → limpieza → *chunking* → *embeddings* → base
  vectorial → recuperación semántica → generación con citación de fuentes.
- **Anti-alucinación:** si ningún fragmento supera el umbral de relevancia, el
  agente responde *"no encontré esta información"* en lugar de inventar.
- **Citación de fuentes:** cada respuesta indica de qué documento salió.
- **Proveedor intercambiable:** Google Gemini (por defecto) u OpenAI, cambiando
  una sola variable de entorno.
- **Interfaz de chat** simple con historial, fuentes y botones de feedback.
- **Registro de ejecución** en formato JSON Lines para auditoría.
- **Listo para OCI:** `Dockerfile` + guía de despliegue en Oracle Cloud.

---

## 🏗️ Arquitectura

```
documentos/                 scripts/ingest.py            src/agent.py
┌───────────────┐          ┌──────────────────┐        ┌───────────────────┐
│ PDF Word XLSX │          │ 1. Extracción    │        │ 4. Recuperación   │
│ PPTX MD CSV   │  ──────► │ 2. Limpieza      │ ─────► │ 5. Generación +   │
│ JSON HTML     │          │ 3. Chunking +    │  Chroma│    citación de    │
│ (7 categorías)│          │    embeddings    │  (DB   │    fuentes        │
└───────────────┘          └──────────────────┘  vect.)└───────────────────┘
                                                              │
                                                     app/streamlit_app.py
                                                       (interfaz de chat)
```

Las etapas se corresponden con las tarjetas del tablero del desafío:

| Etapa del desafío | Dónde está en el código |
|---|---|
| 1. Colecta y organización | `documentos/` (por categoría) + `scripts/generar_documentos.py` |
| 2. Proceso y extracción | `src/ingestion/loaders.py`, `src/ingestion/chunking.py` |
| 3. Indexación | `src/vectorstore.py`, `scripts/ingest.py` |
| 4. Recuperación (RAG) | `src/vectorstore.py::query`, `src/agent.py` |
| 5. Producción y validación | `src/agent.py` (prompt, umbral, fallback) |
| 6. Interfaz y manutención | `app/streamlit_app.py` |
| 7. Deploy en OCI | `Dockerfile`, `docs/deploy_oci.md` |
| 8. Registro de ejecución | `src/logging_utils.py`, `logs/consultas.jsonl` |

---

## 🚀 Puesta en marcha (local)

### 1. Requisitos

- Python 3.11+
- Una API key de [Google AI Studio](https://aistudio.google.com/app/apikey)
  (gratis) **o** de [OpenAI](https://platform.openai.com/api-keys).

### 2. Instalación

```bash
git clone https://github.com/<tu-usuario>/agente_ia_challengue_alura.git
cd agente_ia_challengue_alura

python -m venv .venv && source .venv/bin/activate   # en Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env        # completá tu API key en el archivo .env
```

### 3. Generar los documentos e indexarlos

```bash
python -m scripts.generar_documentos   # crea la base de conocimiento ficticia
python -m scripts.ingest --reset       # extrae, fragmenta e indexa todo
```

### 4. Usar el agente

```bash
# Interfaz de chat (recomendada)
streamlit run app/streamlit_app.py

# O desde la terminal
python -m scripts.preguntar "¿Cuántos días de vacaciones me corresponden?"
```

---

## 💬 Preguntas de ejemplo

- *¿Cuántos días de vacaciones me corresponden con 6 años de antigüedad?* (RH)
- *¿Qué comisión cobra MercadoPago por tarjeta de crédito?* (Financiero)
- *¿Cuánto cuesta el plan Growth?* (Comercial)
- *¿Cómo funciona la facturación automática contra ARCA?* (Operacional)
- *¿Qué datos personales recolecta la empresa?* (Legal)
- *¿Qué endpoints tiene la API de TechRetail?* (Datos y Sistemas)

---

## ⚙️ Configuración

Todas las opciones se controlan por variables de entorno (ver `.env.example`).
Las más importantes:

| Variable | Por defecto | Descripción |
|---|---|---|
| `LLM_PROVIDER` | `gemini` | Proveedor: `gemini` u `openai` |
| `TOP_K` | `5` | Fragmentos recuperados por consulta |
| `MIN_RELEVANCE` | `0.25` | Umbral de relevancia para responder |
| `CHUNK_SIZE` | `800` | Tamaño de cada fragmento |

---

## 📁 Estructura del proyecto

```
agente_ia_challengue_alura/
├── documentos/              # Base de conocimiento (8 formatos, 7 categorías)
├── src/
│   ├── config.py            # Configuración central
│   ├── providers.py         # Capa LLM/embeddings (Gemini/OpenAI)
│   ├── ingestion/           # Extracción, limpieza y chunking
│   ├── vectorstore.py       # Base vectorial (ChromaDB)
│   ├── agent.py             # Orquestación RAG + citación
│   └── logging_utils.py     # Registro de ejecución
├── scripts/
│   ├── generar_documentos.py  # Crea los documentos ficticios
│   ├── ingest.py              # Indexa los documentos
│   └── preguntar.py           # CLI de consulta
├── app/streamlit_app.py     # Interfaz de chat
├── docs/deploy_oci.md       # Guía de despliegue en OCI
├── Dockerfile
├── requirements.txt
└── .env.example
```

---

## ☁️ Despliegue en OCI

El agente se empaqueta con Docker y se despliega en **Oracle Cloud
Infrastructure**. Ver la guía paso a paso en **[`docs/deploy_oci.md`](docs/deploy_oci.md)**
(Container Registry + Container Instances + Object Storage + Vault).

```bash
docker build -t techretail-agente .
docker run -p 8501:8501 --env-file .env techretail-agente
```

---

## 🧪 Sobre los datos

Todos los documentos de `documentos/` son **ficticios** y fueron generados para
este desafío a partir del caso de estudio TechRetail. No representan datos
reales de ninguna empresa ni persona.

---

## 📝 Licencia

Proyecto educativo desarrollado para el Challenge AluraAgente ONE - IA for Tech.
