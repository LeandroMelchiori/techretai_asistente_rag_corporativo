"""
Script de indexación de documentos.

Sincroniza la base vectorial con la carpeta de documentos del perfil: indexa los
documentos nuevos o modificados, saltea los que no cambiaron y quita los que ya
no están (ver src/ingestion/indexar.py).

Uso:
    python -m scripts.ingest              # sincroniza con la carpeta del perfil
    python -m scripts.ingest --reset      # borra la colección y reindexa todo
    tar -c documentos | python -m scripts.ingest --tar -

Con ``--tar -`` los documentos llegan por la entrada estándar como un archivo
tar y se extraen en un directorio temporal: así se indexan en el servidor sin
que formen parte de la imagen ni queden guardados en él.
"""
from __future__ import annotations

import argparse
import sys
import tarfile
import tempfile
from pathlib import Path

# Permite ejecutar el script tanto con -m como directamente.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import vectorstore  # noqa: E402
from src.config import settings  # noqa: E402
from src.ingestion.indexar import documentos_en, sincronizar  # noqa: E402
from src.perfil import perfil_activo  # noqa: E402


def _extraer_tar(flujo, destino: Path) -> Path:
    """Extrae el tar en ``destino`` y devuelve la carpeta de documentos.

    Acepta un tar con la carpeta ``documentos/`` o con las categorías en la raíz.
    El filtro "data" rechaza rutas absolutas, enlaces y archivos fuera de destino.
    """
    with tarfile.open(fileobj=flujo, mode="r|*") as tar:
        tar.extractall(destino, filter="data")
    interna = destino / "documentos"
    return interna if interna.is_dir() else destino


def _indexar(directorio: Path, reset: bool) -> int:
    if not directorio.is_dir():
        print(f"No existe el directorio de documentos: {directorio}")
        return 1
    # Sin esta verificación, una carpeta vacía (o un tar equivocado) vaciaría el índice.
    if not documentos_en(directorio):
        print(f"No se encontraron documentos soportados en {directorio}; el índice no se modifica.")
        return 1

    perfil = perfil_activo()
    print(f"Empresa: {perfil.empresa} (colección {perfil.coleccion})")
    if reset:
        print("Reiniciando la colección...")
        vectorstore.reset_collection()

    r = sincronizar(directorio)
    print(
        f"\nListo. {len(r.nuevos)} nuevos, {len(r.actualizados)} actualizados, "
        f"{len(r.sin_cambios)} sin cambios, {len(r.quitados)} quitados"
        f" ({r.fragmentos} fragmentos indexados)."
    )
    if r.sin_texto:
        print(f"Sin texto extraíble: {', '.join(r.sin_texto)}")
    if r.con_error:
        print(f"Con errores (quedaron como estaban): {', '.join(r.con_error)}")
    print(f"Base vectorial en: {settings.chroma_dir}")
    return 1 if r.con_error else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Indexa los documentos en la base vectorial.")
    parser.add_argument("--reset", action="store_true", help="Reindexa desde cero.")
    parser.add_argument(
        "--tar", metavar="-", choices=["-"],
        help="Lee los documentos como un archivo tar desde la entrada estándar.",
    )
    args = parser.parse_args()

    settings.validate()

    if args.tar:
        with tempfile.TemporaryDirectory(prefix="documentos-") as tmp:
            return _indexar(_extraer_tar(sys.stdin.buffer, Path(tmp)), args.reset)
    return _indexar(settings.docs_dir, args.reset)


if __name__ == "__main__":
    raise SystemExit(main())
