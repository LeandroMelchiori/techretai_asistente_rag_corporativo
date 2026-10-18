"""Herramientas de solo lectura sobre la cuenta de Mercado Libre de la empresa."""
from __future__ import annotations

from typing import List, Optional

from ..conectores.mercadolibre import ESTADOS_PEDIDO, CuentaMercadoLibre
from .base import SIN_PARAMETROS, Herramienta, Resultado

ORIGEN = "Mercado Libre"


def _plural(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


def herramientas_mercadolibre(cuenta: CuentaMercadoLibre) -> List[Herramienta]:
    def preguntas() -> Resultado:
        datos = cuenta.preguntas_sin_responder()
        return Resultado(
            {"total": len(datos), "preguntas": datos},
            _plural(len(datos), "pregunta sin responder", "preguntas sin responder"),
        )

    def pedidos(estado: Optional[str] = None) -> Resultado:
        datos = cuenta.pedidos(estado)
        filtro = f" ({estado.replace('_', ' ')})" if estado else ""
        return Resultado(
            {"total": len(datos), "pedidos": datos},
            _plural(len(datos), "pedido", "pedidos") + filtro,
        )

    def reclamos() -> Resultado:
        datos = cuenta.reclamos_abiertos()
        return Resultado(
            {"total": len(datos), "reclamos": datos},
            _plural(len(datos), "reclamo abierto", "reclamos abiertos"),
        )

    def publicaciones(texto: Optional[str] = None) -> Resultado:
        datos = cuenta.publicaciones(texto)
        return Resultado(
            {"total": len(datos), "publicaciones": datos},
            _plural(len(datos), "publicación", "publicaciones"),
        )

    return [
        Herramienta(
            nombre="ml_preguntas_sin_responder",
            descripcion=(
                "Preguntas de compradores en las publicaciones de Mercado Libre que todavía "
                "no tienen respuesta, de la más antigua a la más reciente."
            ),
            parametros=SIN_PARAMETROS,
            ejecutar=preguntas,
            origen=ORIGEN,
        ),
        Herramienta(
            nombre="ml_pedidos",
            descripcion=(
                "Pedidos (ventas) de Mercado Libre con productos, total, estado del envío y "
                "fecha estimada de entrega. Se puede filtrar por estado; 'demorado' son los "
                "que pasaron la fecha estimada sin entregarse."
            ),
            parametros={
                "type": "object",
                "properties": {
                    "estado": {
                        "type": "string",
                        "enum": [*ESTADOS_PEDIDO, "demorado"],
                        "description": "Filtro opcional por estado del pedido.",
                    }
                },
            },
            ejecutar=pedidos,
            origen=ORIGEN,
        ),
        Herramienta(
            nombre="ml_reclamos_abiertos",
            descripcion=(
                "Reclamos abiertos de compradores en Mercado Libre, con el pedido, los "
                "productos, la fecha de entrega, el motivo y el mensaje del comprador."
            ),
            parametros=SIN_PARAMETROS,
            ejecutar=reclamos,
            origen=ORIGEN,
        ),
        Herramienta(
            nombre="ml_publicaciones",
            descripcion=(
                "Publicaciones de Mercado Libre con precio, stock publicado y estado. "
                "Se puede filtrar por palabras del título."
            ),
            parametros={
                "type": "object",
                "properties": {
                    "texto": {
                        "type": "string",
                        "description": "Palabras del título para filtrar (opcional).",
                    }
                },
            },
            ejecutar=publicaciones,
            origen=ORIGEN,
        ),
    ]
