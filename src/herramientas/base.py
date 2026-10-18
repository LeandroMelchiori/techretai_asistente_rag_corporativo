"""
Herramientas que el modelo puede usar para responder.

Una herramienta tiene un nombre, una descripción y el esquema JSON de sus
argumentos (lo que ve el modelo), y la función que la ejecuta. Todas son de
solo lectura: ninguna modifica datos de la empresa ni de sus cuentas.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List


@dataclass
class Resultado:
    """Lo que devuelve una herramienta.

    ``datos`` es lo que recibe el modelo; ``fuentes`` y ``resumen`` son para
    mostrar en la interfaz qué se consultó.
    """

    datos: Dict[str, Any]
    resumen: str = ""
    fuentes: List[Dict] = field(default_factory=list)


@dataclass(frozen=True)
class Herramienta:
    nombre: str
    descripcion: str
    parametros: Dict[str, Any]
    ejecutar: Callable[..., Resultado]
    # Nombre visible en la interfaz ("Mercado Libre", "Documentos").
    origen: str = ""


SIN_PARAMETROS: Dict[str, Any] = {"type": "object", "properties": {}}
