"""
Base de datos vectorial (ChromaDB, persistente en disco).

Guarda cada fragmento junto con su vector de embedding y sus metadatos
(categoría, archivo de origen, formato). Los embeddings los generamos
nosotros con el proveedor configurado, por eso Chroma se usa sin su función
de embedding interna.
"""
from __future__ import annotations

from typing import Dict, List

import chromadb

from .config import settings
from .providers import embed_texts


def _client() -> "chromadb.ClientAPI":
    settings.chroma_dir.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(settings.chroma_dir))


def get_collection():
    """Devuelve (creando si hace falta) la colección de documentos."""
    client = _client()
    # Distancia coseno: estándar para similitud semántica de textos.
    return client.get_or_create_collection(
        name=settings.collection_name,
        metadata={"hnsw:space": "cosine"},
    )


def reset_collection():
    """Borra y recrea la colección (útil para reindexar desde cero)."""
    client = _client()
    try:
        client.delete_collection(settings.collection_name)
    except Exception:
        pass
    return client.get_or_create_collection(
        name=settings.collection_name,
        metadata={"hnsw:space": "cosine"},
    )


def add_chunks(ids: List[str], textos: List[str], metadatos: List[Dict]) -> None:
    """Genera embeddings de los fragmentos y los inserta en la colección."""
    if not textos:
        return
    coleccion = get_collection()
    vectores = embed_texts(textos, is_query=False)
    coleccion.add(ids=ids, embeddings=vectores, documents=textos, metadatas=metadatos)


def query(pregunta: str, top_k: int | None = None, categoria: str | None = None) -> List[Dict]:
    """Recupera los fragmentos más similares a la pregunta.

    Devuelve una lista de dicts con: texto, metadatos y ``relevancia`` (0-1,
    donde 1 es idéntico). Permite filtrar por categoría vía metadatos.
    """
    top_k = top_k or settings.top_k
    coleccion = get_collection()
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


def stats() -> Dict:
    """Métricas básicas de la colección (para la interfaz)."""
    coleccion = get_collection()
    return {"fragmentos": coleccion.count()}
