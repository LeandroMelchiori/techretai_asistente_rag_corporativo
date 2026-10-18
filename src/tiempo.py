"""Hora de referencia del asistente (Argentina, UTC-3, sin horario de verano)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

HORA_ARGENTINA = timezone(timedelta(hours=-3), "ART")


def ahora() -> datetime:
    return datetime.now(HORA_ARGENTINA)


def fecha(momento: datetime) -> str:
    return momento.astimezone(HORA_ARGENTINA).strftime("%d/%m/%Y %H:%M")


def antiguedad(momento: datetime, referencia: datetime) -> str:
    """Cuánto pasó desde ``momento``, en palabras ("hace 5 horas")."""
    horas = (referencia - momento).total_seconds() / 3600
    if horas < 1:
        return "hace menos de una hora"
    if horas < 48:
        n = int(horas)
        return f"hace {n} hora{'s' if n != 1 else ''}"
    return f"hace {int(horas // 24)} días"
