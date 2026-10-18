"""
Respuestas guardadas para las preguntas sugeridas.

Las tarjetas de inicio son lo que más se usa en la demo. Guardar su respuesta
un tiempo hace que sólo la primera persona consuma cuota de la API; las
siguientes la reciben al instante. Sólo se guardan las preguntas sugeridas:
las que escribe cada persona pueden incluir datos propios y no se comparten.
"""
from __future__ import annotations

import threading
import time
from typing import Callable, Dict, Hashable, Optional, Tuple


class CacheDeRespuestas:
    def __init__(self, duracion_s: float, reloj: Callable[[], float] = time.monotonic) -> None:
        self.duracion_s = duracion_s
        self._reloj = reloj
        self._lock = threading.Lock()
        self._datos: Dict[Hashable, Tuple[float, dict]] = {}

    def obtener(self, clave: Hashable) -> Optional[dict]:
        if self.duracion_s <= 0:
            return None
        with self._lock:
            guardado = self._datos.get(clave)
            if guardado is None:
                return None
            momento, valor = guardado
            if self._reloj() - momento > self.duracion_s:
                del self._datos[clave]
                return None
            return valor

    def guardar(self, clave: Hashable, valor: dict) -> None:
        if self.duracion_s <= 0:
            return
        with self._lock:
            self._datos[clave] = (self._reloj(), valor)
