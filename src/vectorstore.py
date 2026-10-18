"""
Base de datos vectorial (ChromaDB, persistente en disco).

Guarda cada fragmento junto con su vector de embedding y sus metadatos
(categoría, archivo de origen, formato). Los embeddings los generamos
nosotros con el proveedor configurado, por eso Chroma se usa sin su función
de embedding interna.
"""
from __future__ import annotations

from typing import Dict, List, Optional

import chromadb

from .config import settings
from .perfil import Perfil, perfil_activo
from .providers import embed_texts


def _client() -> "chromadb.ClientAPI":
    settings.chroma_dir.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(settings.chroma_dir))


def get_collection(perfil: Optional[Perfil] = None):
    """Devuelve (creando si hace falta) la colección de documentos de la empresa.

    Sin ``perfil``, la del perfil activo (variable ``PERFIL``).
    """
    client = _client()
    # Distancia coseno: estándar para similitud semántica de textos.
    return client.get_or_create_collection(
        name=(perfil or perfil_activo()).coleccion,
        metadata={"hnsw:space": "cosine"},
    )


def reset_collection():
    """Borra y recrea la colección (útil para reindexar desde cero)."""
    client = _client()
    try:
        client.delete_collection(perfil_activo().coleccion)
    except Exception:
        pass
    return get_collection()


def firmas_indexadas() -> Dict[str, str]:
    """Ruta de cada documento indexado -> firma con la que se indexó.

    Los índices anteriores a las firmas devuelven una firma vacía, así que esos
    documentos se reindexan la próxima vez.
    """
    metadatos = get_collection().get(include=["metadatas"])["metadatas"]
    return {m["ruta"]: m.get("firma", "") for m in metadatos if m and "ruta" in m}


def reemplazar_documento(ruta: str, textos: List[str], metadatos: List[Dict]) -> None:
    """Reemplaza todos los fragmentos de un documento por los nuevos.

    Los embeddings se generan antes de borrar: si la API falla, el documento
    conserva su versión anterior en lugar de desaparecer del índice.
    """
    vectores = embed_texts(textos, is_query=False)
    coleccion = get_collection()
    coleccion.delete(where={"ruta": ruta})
    ids = [f"{ruta}::{i}" for i in range(len(textos))]
    coleccion.add(ids=ids, embeddings=vectores, documents=textos, metadatas=metadatos)


def quitar_documento(ruta: str) -> None:
    """Elimina del índice todos los fragmentos de un documento."""
    get_collection().delete(where={"ruta": ruta})


def query(
    pregunta: str,
    top_k: int | None = None,
    categoria: str | None = None,
    perfil: Optional[Perfil] = None,
) -> List[Dict]:
    """Recupera los fragmentos más similares a la pregunta.

    Devuelve una lista de dicts con: texto, metadatos y ``relevancia`` (0-1,
    donde 1 es idéntico). Permite filtrar por categoría vía metadatos.
    """
    top_k = top_k or settings.top_k
    coleccion = get_collection(perfil)
    if coleccion.count() == 0:
        return []

    vector = embed_texts([pregunta], is_query=True)[0]
    filtro = {"categoria": categoria} if categoria else None

    resultado = coleccion.query(
        query_embeddings=[vector],
        n_results=top_k,
        where=filtro,
        include=["documents", "metadatas", "distances"],
    )

    docs = resultado["documents"][0]
    metas = resultado["metadatas"][0]
    distancias = resultado["distances"][0]

    fragmentos = []
    for texto, meta, dist in zip(docs, metas, distancias):
        # Con distancia coseno, relevancia = 1 - distancia.
        fragmentos.append(
            {"texto": texto, "meta": meta, "relevancia": round(1 - dist, 4)}
        )
    return fragmentos


def stats(perfil: Optional[Perfil] = None) -> Dict:
    """Métricas básicas de la colección (para la interfaz)."""
    coleccion = get_collection(perfil)
    return {"fragmentos": coleccion.count()}
