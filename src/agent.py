"""
El agente: orquesta recuperación (RAG) + generación con citación de fuentes
y control de alucinación (etapas 4 y 5 del desafío).

Flujo:
    1. Recupera los fragmentos más relevantes de la base vectorial.
    2. Si ninguno supera el umbral de relevancia -> responde "no encontrado"
       (fallback), sin arriesgar una respuesta inventada.
    3. Arma el contexto con las fuentes y le pide al LLM responder SOLO con
       base en ese contexto, citando el documento de origen.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from . import vectorstore
from .config import settings
from .providers import generate

SYSTEM_PROMPT = """\
Sos el asistente interno de TechRetail Solutions S.R.L., una plataforma SaaS \
de e-commerce para PyMEs y emprendedores en Argentina. Respondés preguntas de \
los colaboradores basándote ÚNICAMENTE en los documentos internos que te paso \
como contexto.

Reglas estrictas:
- Respondé solo con información presente en el CONTEXTO. No uses conocimiento externo.
- Citá siempre la fuente entre corchetes al final de cada afirmación, con el \
nombre del documento, así: [nombre_del_archivo].
- Si el contexto no contiene la información necesaria, decílo claramente: \
"No encontré esta información en los documentos disponibles." No inventes.
- Respondé en español rioplatense, de forma clara y concreta.
"""

FALLBACK = (
    "No encontré esta información en los documentos disponibles. "
    "Te sugiero reformular la pregunta o contactar al área responsable "
    "(por ejemplo, RH, Finanzas o Legal según el tema)."
)


@dataclass
class Respuesta:
    pregunta: str
    texto: str
    fuentes: List[Dict] = field(default_factory=list)
    relevancia_max: float = 0.0
    latencia_ms: int = 0
    contexto_encontrado: bool = True


def _armar_contexto(fragmentos: List[Dict]) -> str:
    """Ensambla los fragmentos recuperados en un bloque de contexto citable."""
    bloques = []
    for i, frag in enumerate(fragmentos, start=1):
        meta = frag["meta"]
        origen = meta.get("archivo", "desconocido")
        categoria = meta.get("categoria", "")
        bloques.append(
            f"--- Fragmento {i} "
            f"(documento: {origen} | categoría: {categoria}) ---\n"
            f"{frag['texto']}"
        )
    return "\n\n".join(bloques)


def responder(pregunta: str, categoria: Optional[str] = None) -> Respuesta:
    """Responde una pregunta del colaborador con RAG + citación de fuentes."""
    inicio = time.time()

    fragmentos = vectorstore.query(pregunta, categoria=categoria)
    relevancia_max = max((f["relevancia"] for f in fragmentos), default=0.0)

    # Control de alucinación: si nada es suficientemente relevante, fallback.
    relevantes = [f for f in fragmentos if f["relevancia"] >= settings.min_relevance]
    if not relevantes:
        return Respuesta(
            pregunta=pregunta,
            texto=FALLBACK,
            fuentes=[],
            relevancia_max=relevancia_max,
            latencia_ms=int((time.time() - inicio) * 1000),
            contexto_encontrado=False,
        )

    contexto = _armar_contexto(relevantes)
    user_prompt = (
        f"CONTEXTO (documentos internos de TechRetail):\n\n{contexto}\n\n"
        f"PREGUNTA DEL COLABORADOR: {pregunta}\n\n"
        f"Respondé siguiendo estrictamente las reglas del sistema."
    )
    texto = generate(SYSTEM_PROMPT, user_prompt)

    # Fuentes únicas (documento + categoría) para mostrar en la interfaz.
    vistos = set()
    fuentes = []
    for f in relevantes:
        clave = (f["meta"].get("archivo"), f["meta"].get("categoria"))
        if clave not in vistos:
            vistos.add(clave)
            fuentes.append(
                {
                    "archivo": f["meta"].get("archivo"),
                    "categoria": f["meta"].get("categoria"),
                    "formato": f["meta"].get("formato"),
                    "relevancia": f["relevancia"],
                }
            )

    return Respuesta(
        pregunta=pregunta,
        texto=texto,
        fuentes=fuentes,
        relevancia_max=relevancia_max,
        latencia_ms=int((time.time() - inicio) * 1000),
        contexto_encontrado=True,
    )
