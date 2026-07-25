"""
CLI para consultar al agente desde la terminal (útil para pruebas y para
generar registros de ejecución).

Uso:
    python -m scripts.preguntar "¿Cuántos días de vacaciones tengo?"
    python -m scripts.preguntar            # modo interactivo
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agent import responder  # noqa: E402
from src.config import settings  # noqa: E402
from src.logging_utils import registrar  # noqa: E402


def _preguntar(texto: str) -> None:
    resp = responder(texto)
    registrar(resp)
    print("\n" + resp.texto)
    if resp.fuentes:
        print("\nFuentes:")
        for f in resp.fuentes:
            print(f"  - {f['archivo']} [{f['categoria']}] (relevancia {f['relevancia']:.2f})")
    print(f"\n(latencia: {resp.latencia_ms} ms | proveedor: {settings.provider})")


def main() -> int:
    settings.validate()
    if len(sys.argv) > 1:
        _preguntar(" ".join(sys.argv[1:]))
        return 0

    print("Asistente TechRetail (escribí 'salir' para terminar)\n")
    while True:
        try:
            texto = input("Vos> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if texto.lower() in ("salir", "exit", "quit", ""):
            break
        _preguntar(texto)
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
