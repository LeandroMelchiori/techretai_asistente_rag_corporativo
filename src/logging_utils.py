"""
Registro de ejecución del agente.

Cada consulta se guarda como una línea JSON (formato JSON Lines) con la
pregunta, la respuesta, las fuentes usadas, la relevancia, el timestamp y la
latencia. Esto permite auditoría, depuración y mejora continua.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from .agent import Respuesta
from .config import settings
from .perfil import perfil_activo


def registrar(respuesta: Respuesta, feedback: str | None = None) -> None:
    """Agrega una línea JSON al archivo de log de consultas."""
    settings.log_file.parent.mkdir(parents=True, exist_ok=True)
    registro = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "perfil": perfil_activo().id,
        "proveedor": settings.provider,
        "pregunta": respuesta.pregunta,
        "respuesta": respuesta.texto,
        "contexto_encontrado": respuesta.contexto_encontrado,
        "relevancia_max": respuesta.relevancia_max,
        "latencia_ms": respuesta.latencia_ms,
        "fuentes": [f.get("archivo") for f in respuesta.fuentes],
        "feedback": feedback,
    }
    with settings.log_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(registro, ensure_ascii=False) + "\n")
