"""
Límites de uso para proteger la cuota (y el costo) de la API del LLM.

La app es pública: sin límites, cualquiera podría agotar la cuota de la API key
con preguntas automatizadas. Se aplican dos topes en memoria, que se reinician
con el proceso (suficiente para este volumen):

    - por cliente: N preguntas en una ventana deslizante de M minutos;
    - global: N preguntas por día entre todos los clientes.

Un valor 0 desactiva el tope correspondiente.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Callable, Deque, Dict

DIA_S = 24 * 60 * 60
_MAX_CLIENTES = 10_000  # por encima de esto se purgan los clientes inactivos


@dataclass
class Decision:
    permitido: bool
    espera_s: int = 0
    motivo: str = ""  # "cliente" | "global" cuando no se permite


class LimitadorDeConsultas:
    def __init__(
        self,
        por_cliente: int,
        ventana_s: int,
        por_dia: int,
        reloj: Callable[[], float] = time.monotonic,
    ) -> None:
        self.por_cliente = por_cliente
        self.ventana_s = ventana_s
        self.por_dia = por_dia
        self._reloj = reloj
        self._lock = threading.Lock()
        self._clientes: Dict[str, Deque[float]] = defaultdict(deque)
        self._global: Deque[float] = deque()

    def permitir(self, cliente: str) -> Decision:
        """Registra una consulta del cliente si entra en los topes."""
        ahora = self._reloj()
        with self._lock:
            _purgar(self._global, ahora - DIA_S)
            if self.por_dia and len(self._global) >= self.por_dia:
                return Decision(False, _espera(self._global[0] + DIA_S, ahora), "global")

            if len(self._clientes) > _MAX_CLIENTES:
                self._purgar_clientes(ahora)
            marcas = self._clientes[cliente]
            _purgar(marcas, ahora - self.ventana_s)
            if self.por_cliente and len(marcas) >= self.por_cliente:
                return Decision(False, _espera(marcas[0] + self.ventana_s, ahora), "cliente")

            marcas.append(ahora)
            self._global.append(ahora)
            return Decision(True)

    def _purgar_clientes(self, ahora: float) -> None:
        for cliente in list(self._clientes):
            _purgar(self._clientes[cliente], ahora - self.ventana_s)
            if not self._clientes[cliente]:
                del self._clientes[cliente]


def _purgar(marcas: Deque[float], limite: float) -> None:
    while marcas and marcas[0] <= limite:
        marcas.popleft()


def _espera(libre_en: float, ahora: float) -> int:
    return max(1, int(libre_en - ahora + 0.999))
