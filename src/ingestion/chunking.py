"""
Limpieza del texto y división en fragmentos (chunking).

Se usa una estrategia por tamaño con superposición, pero respetando en lo
posible los límites de párrafo para no cortar ideas por la mitad. El tamaño
se mide en tokens (con tiktoken) para que los fragmentos entren cómodos en
el contexto del LLM.
"""
from __future__ import annotations

import re
from typing import List

from ..config import settings

# tiktoken (de OpenAI) da un conteo de tokens preciso, pero su vocabulario se
# descarga la primera vez, lo que puede fallar en redes restringidas. Por eso
# la carga es perezosa y con un fallback local basado en palabras, de modo que
# el chunking siga funcionando sin acceso a internet.
_ENC = None
_ENC_INTENTADO = False


def _encoder():
    global _ENC, _ENC_INTENTADO
    if not _ENC_INTENTADO:
        _ENC_INTENTADO = True
        try:
            import tiktoken

            _ENC = tiktoken.get_encoding("cl100k_base")
        except Exception:
            _ENC = None  # Sin tiktoken -> se usa el estimador por palabras.
    return _ENC


def limpiar_texto(texto: str) -> str:
    """Elimina ruido común de la extracción sin alterar el contenido."""
    # Normaliza saltos de línea y espacios múltiples.
    texto = texto.replace("\r\n", "\n").replace("\r", "\n")
    # Colapsa 3+ saltos de línea en 2 (separación de párrafos).
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    # Colapsa espacios/tabs repetidos.
    texto = re.sub(r"[ \t]{2,}", " ", texto)
    # Quita espacios al final de cada línea.
    texto = "\n".join(linea.rstrip() for linea in texto.split("\n"))
    return texto.strip()


def _contar_tokens(texto: str) -> int:
    enc = _encoder()
    if enc is not None:
        return len(enc.encode(texto))
    # Estimación: en español ~0,75 palabras por token -> tokens ≈ palabras / 0,75.
    return int(len(texto.split()) / 0.75) + 1


def _partir_texto_largo(texto: str, chunk_size: int, overlap: int) -> List[str]:
    """Parte un texto que excede el tamaño objetivo, con o sin tiktoken."""
    enc = _encoder()
    paso = max(chunk_size - overlap, 1)
    if enc is not None:
        ids = enc.encode(texto)
        return [
            enc.decode(ids[i : i + chunk_size]).strip()
            for i in range(0, len(ids), paso)
        ]
    # Fallback por palabras: tamaño objetivo en "palabras equivalentes".
    palabras = texto.split()
    palabras_por_chunk = max(int(chunk_size * 0.75), 1)
    palabras_paso = max(int(paso * 0.75), 1)
    return [
        " ".join(palabras[i : i + palabras_por_chunk]).strip()
        for i in range(0, len(palabras), palabras_paso)
    ]


def dividir_en_chunks(
    texto: str,
    chunk_size: int | None = None,
    overlap: int | None = None,
) -> List[str]:
    """Divide el texto en fragmentos de ~chunk_size tokens con superposición.

    Agrupa párrafos completos hasta llegar al tamaño objetivo; si un párrafo
    por sí solo excede el tamaño, lo parte por tokens.
    """
    chunk_size = chunk_size or settings.chunk_size
    overlap = overlap or settings.chunk_overlap

    texto = limpiar_texto(texto)
    if not texto:
        return []

    parrafos = [p.strip() for p in texto.split("\n\n") if p.strip()]
    chunks: List[str] = []
    actual: List[str] = []
    tokens_actual = 0

    def cerrar_chunk():
        nonlocal actual, tokens_actual
        if actual:
            chunks.append("\n\n".join(actual))
            actual = []
            tokens_actual = 0

    for parrafo in parrafos:
        t = _contar_tokens(parrafo)

        # Párrafo gigante: se parte en trozos más chicos.
        if t > chunk_size:
            cerrar_chunk()
            chunks.extend(_partir_texto_largo(parrafo, chunk_size, overlap))
            continue

        # Si sumar el párrafo excede el tamaño, cierro el chunk actual
        # arrastrando algo de superposición para mantener continuidad.
        if tokens_actual + t > chunk_size and actual:
            solapamiento = actual[-1] if actual else ""
            cerrar_chunk()
            if overlap > 0 and solapamiento:
                actual = [solapamiento]
                tokens_actual = _contar_tokens(solapamiento)

        actual.append(parrafo)
        tokens_actual += t

    cerrar_chunk()
    return chunks
