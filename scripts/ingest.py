"""
Script de indexación (etapas 1 a 3 del desafío).

Recorre el directorio de documentos, extrae y limpia el texto de cada archivo,
lo divide en fragmentos, genera los embeddings y los guarda en la base
vectorial. La categoría se deriva de la subcarpeta (documentos/<categoria>/...),
que funciona como metadato para filtrar búsquedas.

Uso:
    python -m scripts.ingest            # indexa incrementalmente
    python -m scripts.ingest --reset    # borra la colección y reindexa todo
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Permite ejecutar el script tanto con -m como directamente.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import vectorstore  # noqa: E402
from src.config import settings  # noqa: E402
from src.ingestion.chunking import dividir_en_chunks  # noqa: E402
from src.ingestion.loaders import SUPPORTED_EXTENSIONS, extract_text  # noqa: E402


def _categoria_de(path: Path) -> str:
    """La categoría es la primera subcarpeta bajo documentos/."""
    rel = path.relative_to(settings.docs_dir)
    return rel.parts[0] if len(rel.parts) > 1 else "general"


def main() -> int:
    parser = argparse.ArgumentParser(description="Indexa los documentos en la base vectorial.")
    parser.add_argument("--reset", action="store_true", help="Reindexa desde cero.")
    args = parser.parse_args()

    settings.validate()

    if not settings.docs_dir.exists():
        print(f"No existe el directorio de documentos: {settings.docs_dir}")
        return 1

    if args.reset:
        print("Reiniciando la colección...")
        vectorstore.reset_collection()

    archivos = [
        p
        for p in sorted(settings.docs_dir.rglob("*"))
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
    ]
    if not archivos:
        print(f"No se encontraron documentos soportados en {settings.docs_dir}")
        return 1

    total_chunks = 0
    for archivo in archivos:
        try:
            texto = extract_text(archivo)
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠️  Error extrayendo {archivo.name}: {e}")
            continue

        chunks = dividir_en_chunks(texto)
        if not chunks:
            print(f"  ⏭️  {archivo.name}: sin texto extraíble, se omite.")
            continue

        categoria = _categoria_de(archivo)
        nombre_rel = str(archivo.relative_to(settings.docs_dir))
        ids = [f"{nombre_rel}::{i}" for i in range(len(chunks))]
        metadatos = [
            {
                "archivo": archivo.name,
                "ruta": nombre_rel,
                "categoria": categoria,
                "formato": archivo.suffix.lower().lstrip("."),
                "chunk": i,
            }
            for i in range(len(chunks))
        ]
        vectorstore.add_chunks(ids, chunks, metadatos)
        total_chunks += len(chunks)
        print(f"  ✅ {nombre_rel}  [{categoria}]  ->  {len(chunks)} fragmentos")

    print(f"\nListo. {len(archivos)} archivos, {total_chunks} fragmentos indexados.")
    print(f"Base vectorial en: {settings.chroma_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
