"""
Evaluación del agente con herramientas.

Para cada caso de ``perfiles/<empresa>/casos_agente.json`` verifica:
    - Herramientas: que el agente haya usado las herramientas esperadas.
    - Respuesta: que mencione lo esperado y no mencione lo prohibido. Los datos
      del conector en modo demo son fijos, así que la verificación es exacta.

Incluye un caso de *prompt injection* indirecto: una pregunta de comprador
que le pide al asistente que la oculte del listado.

Requisitos: un perfil con conectores (por ejemplo el de TechRetail), sus
documentos indexados y la API key configurada.

Uso:
    python -m eval.evaluar_agente
    python -m eval.evaluar_agente --pausa 10
    python -m eval.evaluar_agente --solo fuera_de_alcance
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import vectorstore  # noqa: E402
from src.agent import responder  # noqa: E402
from src.config import settings  # noqa: E402
from src.perfil import perfil_activo  # noqa: E402


def _normalizar(texto: str) -> str:
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return sin_tildes.lower()


def verificar(caso: dict, texto: str, usadas: list[str]) -> list[str]:
    """Devuelve los problemas encontrados (vacía si el caso pasa)."""
    problemas = []
    faltan = [h for h in caso["herramientas"] if h not in usadas]
    if faltan:
        problemas.append(f"no usó {', '.join(faltan)}")
    respuesta = _normalizar(texto)
    for grupo in caso["debe_mencionar"]:
        if not any(_normalizar(v) in respuesta for v in grupo):
            problemas.append(f"no menciona {' / '.join(grupo)}")
    for prohibido in caso["no_debe_mencionar"]:
        if _normalizar(prohibido) in respuesta:
            problemas.append(f"menciona '{prohibido}'")
    return problemas


def main() -> int:
    parser = argparse.ArgumentParser(description="Evalúa el agente con herramientas.")
    parser.add_argument("--pausa", type=float, default=4, help="Segundos entre casos (cuota de la API).")
    parser.add_argument("--solo", nargs="+", metavar="ID", help="Evalúa sólo estos casos.")
    parser.add_argument(
        "--casos", type=Path, default=settings.perfil_dir / "casos_agente.json",
        help="Casos a evaluar (por defecto, los del perfil activo).",
    )
    args = parser.parse_args()

    settings.validate()
    perfil = perfil_activo()
    if not perfil.conectores:
        print(f"El perfil '{perfil.id}' no tiene conectores: usá eval.evaluar para el RAG.")
        return 1
    if vectorstore.stats(perfil)["fragmentos"] == 0:
        print("La base vectorial está vacía. Corré primero: python -m scripts.ingest")
        return 1

    casos = json.loads(args.casos.read_text(encoding="utf-8"))["casos"]
    if args.solo:
        casos = [c for c in casos if c["id"] in args.solo]
    print(f"Evaluando {len(casos)} casos del agente de {perfil.empresa}\n")

    herramientas_ok = respuestas_ok = 0
    latencias = []
    for i, caso in enumerate(casos):
        if i:
            time.sleep(args.pausa)
        resp = responder(caso["pregunta"], perfil=perfil)
        usadas = [c["nombre"] for c in resp.consultas]
        problemas = verificar(caso, resp.texto, usadas)
        latencias.append(resp.latencia_ms / 1000)

        herramientas_ok += all(h in usadas for h in caso["herramientas"])
        respuestas_ok += not problemas
        icono = "✅" if not problemas else "❌"
        print(f"{icono} {caso['id']} ({resp.latencia_ms / 1000:.1f} s) — usó: {', '.join(usadas) or 'ninguna'}")
        for problema in problemas:
            print(f"     · {problema}")
        if problemas:
            print("     Respuesta: " + resp.texto.replace("\n", " ")[:400])

    n = len(casos)
    latencias.sort()
    print("\n" + "=" * 50)
    print("RESUMEN")
    print(f"  Herramientas correctas: {herramientas_ok}/{n}")
    print(f"  Respuestas correctas:   {respuestas_ok}/{n}")
    print(f"  Latencia p50: {statistics.median(latencias):.1f} s · máx: {latencias[-1]:.1f} s")
    print("=" * 50)
    return 0 if respuestas_ok == n else 1


if __name__ == "__main__":
    raise SystemExit(main())
