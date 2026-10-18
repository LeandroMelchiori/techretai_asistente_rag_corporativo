"""Herramienta de búsqueda en los documentos internos (el RAG, como herramienta)."""
from __future__ import annotations

from typing import Callable, Dict, List, Optional, Tuple

from ..perfil import Perfil
from .base import Herramienta, Resultado

ORIGEN = "Documentos"

# (consulta, categoría, perfil) -> (fragmentos relevantes, relevancia máxima)
Recuperar = Callable[[str, Optional[str], Perfil], Tuple[List[Dict], float]]


def herramienta_documentos(
    perfil: Perfil,
    recuperar: Recuperar,
    fuentes_de: Callable[[List[Dict]], List[Dict]],
    sanitizar: Callable[[str], str],
) -> Herramienta:
    """``buscar_documentos`` con la misma recuperación y umbral que el RAG directo."""

    def buscar(consulta: str, categoria: Optional[str] = None) -> Resultado:
        relevantes, _ = recuperar(consulta, categoria or None, perfil)
        if not relevantes:
            return Resultado(
                {"fragmentos": [], "aviso": "No hay documentos relevantes para esta consulta."},
                "sin resultados",
            )
        fuentes = fuentes_de(relevantes)
        return Resultado(
            {
                "fragmentos": [
                    {
                        "documento": f["meta"].get("archivo"),
                        "categoria": perfil.categoria(f["meta"].get("categoria", "")),
                        "texto": sanitizar(f["texto"]),
                    }
                    for f in relevantes
                ]
            },
            f"{len(fuentes)} documento{'s' if len(fuentes) != 1 else ''}",
            fuentes,
        )

    propiedades = {
        "consulta": {
            "type": "string",
            "description": "Qué buscar, en lenguaje natural (por ejemplo, la pregunta del colaborador).",
        }
    }
    if perfil.categorias:
        propiedades["categoria"] = {
            "type": "string",
            "enum": list(perfil.categorias),
            "description": "Área opcional para acotar la búsqueda.",
        }
    return Herramienta(
        nombre="buscar_documentos",
        descripcion=(
            f"Busca en los documentos internos de {perfil.empresa}: políticas, "
            "procedimientos, precios, condiciones y guías de trabajo."
        ),
        parametros={"type": "object", "properties": propiedades, "required": ["consulta"]},
        ejecutar=buscar,
        origen=ORIGEN,
    )
