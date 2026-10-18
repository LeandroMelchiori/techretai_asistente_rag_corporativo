"""
Sincronización del índice con la carpeta de documentos.

Cada documento se indexa con una *firma* (hash de su contenido y de la
configuración que afecta a sus fragmentos y embeddings). Al sincronizar:

    - los documentos sin cambios se saltean (no se vuelven a generar embeddings,
      que con la API de Gemini cuestan una llamada por fragmento);
    - los nuevos o modificados reemplazan todos sus fragmentos anteriores;
    - los que ya no están en la carpeta se quitan del índice.

La categoría se deriva de la subcarpeta (documentos/<categoria>/...) y funciona
como metadato para filtrar búsquedas.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List

from .. import vectorstore
from ..config import settings
from .chunking import dividir_en_chunks
from .loaders import SUPPORTED_EXTENSIONS, extract_text

# Subirla obliga a reindexar todo cuando cambia la extracción o el chunking.
VERSION_INDEXADO = 1


@dataclass
class Resumen:
    nuevos: List[str] = field(default_factory=list)
    actualizados: List[str] = field(default_factory=list)
    sin_cambios: List[str] = field(default_factory=list)
    quitados: List[str] = field(default_factory=list)
    sin_texto: List[str] = field(default_factory=list)
    con_error: List[str] = field(default_factory=list)
    fragmentos: int = 0


def firma(contenido: bytes) -> str:
    """Identifica el contenido del documento y la configuración con que se indexa."""
    h = hashlib.sha256(contenido)
    h.update(
        f"|v{VERSION_INDEXADO}|{settings.provider}|{settings.embed_model}"
        f"|{settings.chunk_size}|{settings.chunk_overlap}".encode()
    )
    return h.hexdigest()[:16]


def categoria_de(ruta: str) -> str:
    """La categoría es la primera subcarpeta bajo documentos/."""
    partes = ruta.split("/")
    return partes[0] if len(partes) > 1 else "general"


def documentos_en(directorio: Path) -> Dict[str, Path]:
    """Ruta relativa (con '/') -> archivo, para los formatos soportados."""
    return {
        p.relative_to(directorio).as_posix(): p
        for p in sorted(directorio.rglob("*"))
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
    }


def sincronizar(directorio: Path, avisar: Callable[[str], None] = print) -> Resumen:
    """Deja el índice igual a los documentos de ``directorio``."""
    resumen = Resumen()
    actuales = documentos_en(directorio)
    indexados = vectorstore.firmas_indexadas()

    for ruta in sorted(set(indexados) - set(actuales)):
        vectorstore.quitar_documento(ruta)
        resumen.quitados.append(ruta)
        avisar(f"  🗑️  {ruta}: ya no está, se quitan sus fragmentos")

    for ruta, archivo in actuales.items():
        firma_actual = firma(archivo.read_bytes())
        if indexados.get(ruta) == firma_actual:
            resumen.sin_cambios.append(ruta)
            continue

        try:
            chunks = dividir_en_chunks(extract_text(archivo))
        except Exception as e:  # noqa: BLE001
            # Se conserva lo que ya estaba indexado: mejor una versión vieja que ninguna.
            resumen.con_error.append(ruta)
            avisar(f"  ⚠️  {ruta}: error al extraer el texto ({e}); queda como estaba")
            continue

        if not chunks:
            if ruta in indexados:
                vectorstore.quitar_documento(ruta)
            resumen.sin_texto.append(ruta)
            avisar(f"  ⏭️  {ruta}: sin texto extraíble (¿PDF escaneado?), se omite")
            continue

        categoria = categoria_de(ruta)
        metadatos = [
            {
                "archivo": archivo.name,
                "ruta": ruta,
                "categoria": categoria,
                "formato": archivo.suffix.lower().lstrip("."),
                "chunk": i,
                "firma": firma_actual,
            }
            for i in range(len(chunks))
        ]
        vectorstore.reemplazar_documento(ruta, chunks, metadatos)
        resumen.fragmentos += len(chunks)
        if ruta in indexados:
            resumen.actualizados.append(ruta)
            avisar(f"  🔄 {ruta}  [{categoria}]  ->  {len(chunks)} fragmentos")
        else:
            resumen.nuevos.append(ruta)
            avisar(f"  ✅ {ruta}  [{categoria}]  ->  {len(chunks)} fragmentos")

    return resumen
