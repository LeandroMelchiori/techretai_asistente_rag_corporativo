"""
Conector de Mercado Libre (solo lectura).

``CuentaMercadoLibre`` define lo que el asistente puede consultar de la cuenta
del vendedor. ``MercadoLibreDemo`` lo implementa con datos ficticios para la
demo pública y para la evaluación (siempre da los mismos resultados); la
conexión a la API real implementa la misma interfaz.

Los textos de compradores (preguntas y reclamos) se devuelven tal cual: son
datos no confiables y el agente los trata como tales.
"""
from __future__ import annotations

import json
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Dict, List, Optional, Protocol

from .. import tiempo

ESTADOS_PEDIDO = {
    "pendiente_de_envio": "Pendiente de envío",
    "en_camino": "En camino",
    "entregado": "Entregado",
    "cancelado": "Cancelado",
}


class CuentaMercadoLibre(Protocol):
    def preguntas_sin_responder(self) -> List[Dict]: ...

    def pedidos(self, estado: Optional[str] = None) -> List[Dict]: ...

    def reclamos_abiertos(self) -> List[Dict]: ...

    def publicaciones(self, texto: Optional[str] = None) -> List[Dict]: ...


def pesos(monto: float) -> str:
    return "$" + f"{monto:,.0f}".replace(",", ".")


def _normalizar(texto: str) -> str:
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return sin_tildes.lower()


class MercadoLibreDemo:
    """Cuenta ficticia. Los tiempos del archivo son relativos a ``ahora``."""

    def __init__(self, archivo: Path, ahora: Callable[[], datetime] = tiempo.ahora):
        self._datos = json.loads(archivo.read_text(encoding="utf-8"))
        self._ahora = ahora
        self._publicaciones = {p["id"]: p for p in self._datos["publicaciones"]}

    def _hace(self, horas: float) -> datetime:
        return self._ahora() - timedelta(hours=horas)

    def preguntas_sin_responder(self) -> List[Dict]:
        ahora = self._ahora()
        preguntas = sorted(self._datos["preguntas"], key=lambda q: q["hace_horas"], reverse=True)
        return [
            {
                "id": q["id"],
                "publicacion": self._publicaciones[q["publicacion"]]["titulo"],
                "pregunta": q["texto"],
                "recibida": tiempo.fecha(self._hace(q["hace_horas"])),
                "antiguedad": tiempo.antiguedad(self._hace(q["hace_horas"]), ahora),
            }
            for q in preguntas
        ]

    def _pedido(self, p: Dict) -> Dict:
        ahora = self._ahora()
        items = [(self._publicaciones[i["publicacion"]], i["cantidad"]) for i in p["items"]]
        entrega = self._hace(-p["entrega_estimada_en_horas"]) if "entrega_estimada_en_horas" in p else None
        demorado = p["estado"] in ("pendiente_de_envio", "en_camino") and entrega is not None and entrega < ahora
        pedido = {
            "id": p["id"],
            "comprador": p["comprador"],
            "productos": [f"{pub['titulo']} x{cant}" for pub, cant in items],
            "total": pesos(sum(pub["precio"] * cant for pub, cant in items)),
            "pagado": tiempo.fecha(self._hace(p["pagado_hace_horas"])),
            "estado": ESTADOS_PEDIDO[p["estado"]],
            "demorado": demorado,
        }
        if entrega is not None:
            pedido["entrega_estimada"] = tiempo.fecha(entrega)
        if "entregado_hace_horas" in p:
            pedido["entregado"] = tiempo.fecha(self._hace(p["entregado_hace_horas"]))
        return pedido

    def pedidos(self, estado: Optional[str] = None) -> List[Dict]:
        pedidos = [self._pedido(p) for p in self._datos["pedidos"]]
        if estado == "demorado":
            return [p for p in pedidos if p["demorado"]]
        if estado:
            return [p for p in pedidos if p["estado"] == ESTADOS_PEDIDO.get(estado)]
        return pedidos

    def reclamos_abiertos(self) -> List[Dict]:
        ahora = self._ahora()
        pedidos = {p["id"]: p for p in self._datos["pedidos"]}
        reclamos = []
        for r in self._datos["reclamos"]:
            pedido = self._pedido(pedidos[r["pedido"]])
            reclamos.append({
                "id": r["id"],
                "pedido": r["pedido"],
                "productos": pedido["productos"],
                "entregado": pedido.get("entregado"),
                "motivo": r["motivo"],
                "mensaje_del_comprador": r["texto"],
                "abierto": tiempo.fecha(self._hace(r["hace_horas"])),
                "antiguedad": tiempo.antiguedad(self._hace(r["hace_horas"]), ahora),
            })
        return reclamos

    def publicaciones(self, texto: Optional[str] = None) -> List[Dict]:
        buscado = _normalizar(texto or "")
        return [
            {
                "id": p["id"],
                "titulo": p["titulo"],
                "precio": pesos(p["precio"]),
                "stock_publicado": p["stock"],
                "estado": p["estado"],
            }
            for p in self._datos["publicaciones"]
            if all(palabra in _normalizar(p["titulo"]) for palabra in buscado.split())
        ]
