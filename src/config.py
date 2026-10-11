"""
Configuración central del agente.

Lee las variables de entorno (desde un archivo .env si existe) y expone
un objeto `settings` con valores por defecto sensatos. De esta forma, el
resto del código nunca lee ``os.environ`` directamente.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Carga el .env de la raíz del proyecto (si existe). En producción las
# variables suelen venir del entorno del contenedor / OCI Vault.
load_dotenv()

# Raíz del repositorio (dos niveles arriba de este archivo: src/config.py).
BASE_DIR = Path(__file__).resolve().parent.parent


def _get(name: str, default: str) -> str:
    value = os.getenv(name)
    return value if value not in (None, "") else default


@dataclass
class Settings:
    # --- Proveedor ---
    provider: str = field(default_factory=lambda: _get("LLM_PROVIDER", "gemini").lower())

    # --- Credenciales ---
    google_api_key: str = field(default_factory=lambda: _get("GOOGLE_API_KEY", ""))
    openai_api_key: str = field(default_factory=lambda: _get("OPENAI_API_KEY", ""))

    # --- Modelos ---
    gemini_chat_model: str = field(default_factory=lambda: _get("GEMINI_CHAT_MODEL", "gemini-3.5-flash-lite"))
    gemini_embed_model: str = field(default_factory=lambda: _get("GEMINI_EMBED_MODEL", "gemini-embedding-2"))
    openai_chat_model: str = field(default_factory=lambda: _get("OPENAI_CHAT_MODEL", "gpt-4o-mini"))
    openai_embed_model: str = field(default_factory=lambda: _get("OPENAI_EMBED_MODEL", "text-embedding-3-small"))

    # --- Parámetros del RAG ---
    chunk_size: int = field(default_factory=lambda: int(_get("CHUNK_SIZE", "800")))
    chunk_overlap: int = field(default_factory=lambda: int(_get("CHUNK_OVERLAP", "120")))
    top_k: int = field(default_factory=lambda: int(_get("TOP_K", "5")))
    # Calibrado con eval/preguntas_eval.json para gemini-embedding-2: la similitud
    # coseno tiene un piso alto (~0,5 incluso entre textos sin relación), así que
    # el umbral absoluto sólo descarta lo claramente ajeno y el margen deja fuera
    # los fragmentos muy por debajo del mejor resultado.
    min_relevance: float = field(default_factory=lambda: float(_get("MIN_RELEVANCE", "0.53")))
    relevance_margin: float = field(default_factory=lambda: float(_get("RELEVANCE_MARGIN", "0.08")))

    # --- Límites de uso (protegen la cuota de la API key; 0 = sin límite) ---
    rate_limit_per_client: int = field(default_factory=lambda: int(_get("RATE_LIMIT_PER_CLIENT", "15")))
    rate_limit_window_min: int = field(default_factory=lambda: int(_get("RATE_LIMIT_WINDOW_MIN", "10")))
    rate_limit_daily: int = field(default_factory=lambda: int(_get("RATE_LIMIT_DAILY", "300")))
    max_question_chars: int = field(default_factory=lambda: int(_get("MAX_QUESTION_CHARS", "500")))

    # --- Rutas ---
    docs_dir: Path = field(default_factory=lambda: BASE_DIR / _get("DOCS_DIR", "documentos"))
    chroma_dir: Path = field(default_factory=lambda: BASE_DIR / _get("CHROMA_DIR", "data/chroma"))
    log_file: Path = field(default_factory=lambda: BASE_DIR / _get("LOG_FILE", "logs/consultas.jsonl"))

    # Nombre de la colección dentro de Chroma.
    collection_name: str = "techretail_docs"

    def validate(self) -> None:
        """Verifica que exista la credencial del proveedor seleccionado."""
        if self.provider == "gemini" and not self.google_api_key:
            raise RuntimeError(
                "Falta GOOGLE_API_KEY. Copiá .env.example a .env y completá tu key, "
                "o exportá la variable de entorno."
            )
        if self.provider == "openai" and not self.openai_api_key:
            raise RuntimeError(
                "Falta OPENAI_API_KEY. Copiá .env.example a .env y completá tu key, "
                "o exportá la variable de entorno."
            )
        if self.provider not in ("gemini", "openai"):
            raise RuntimeError(
                f"LLM_PROVIDER='{self.provider}' no soportado. Usá 'gemini' u 'openai'."
            )


settings = Settings()
