"""
Evaluación del agente RAG.

Mide la calidad de la RECUPERACIÓN (¿trae el documento correcto?) y del
CONTROL DE ALUCINACIÓN (¿rechaza lo que no está en la base?), usando el set
de casos del perfil activo (`perfiles/<empresa>/preguntas_eval.json`).

Métricas:
    - Hit@k:  proporción de preguntas donde el documento esperado aparece
              entre los k fragmentos recuperados.
    - MRR:    Mean Reciprocal Rank; premia que el documento correcto aparezca
              lo más arriba posible (1/posición).
    - Rechazo correcto: proporción de preguntas fuera de alcance que el agente
              rechaza correctamente (relevancia máxima por debajo del umbral).

Requisitos: haber indexado los documentos (`python -m scripts.ingest`)
y tener la API key configurada.

Uso:
    python -m eval.evaluar
    python -m eval.evaluar --top-k 5
    PERFIL=perfiles/nogal python -m eval.evaluar
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import vectorstore  # noqa: E402
from src.config import settings  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Evalúa la recuperación del agente.")
    parser.add_argument("--top-k", type=int, default=settings.top_k)
    parser.add_argument(
        "--casos", type=Path, default=settings.perfil_dir / "preguntas_eval.json",
        help="Set de evaluación (por defecto, el del perfil activo).",
    )
    args = parser.parse_args()

    settings.validate()
    if vectorstore.stats()["fragmentos"] == 0:
        print("La base vectorial está vacía. Corré primero: python -m scripts.ingest")
        return 1

    casos = json.loads(args.casos.read_text(encoding="utf-8"))["casos"]
    en_alcance = [c for c in casos if c["fuentes"]]
    fuera_alcance = [c for c in casos if not c["fuentes"]]

    print(f"Evaluando {len(casos)} casos (top_k={args.top_k})\n")

    # --- Recuperación (casos en alcance) ---
    hits = 0
    suma_rr = 0.0
    print("RECUPERACIÓN")
    for c in en_alcance:
        frags = vectorstore.query(c["pregunta"], top_k=args.top_k)
        recuperados = [f["meta"]["archivo"] for f in frags]
        # Posición (1-indexada) del primer documento esperado.
        rank = next(
            (i + 1 for i, arch in enumerate(recuperados) if arch in c["fuentes"]),
            None,
        )
        if rank:
            hits += 1
            suma_rr += 1 / rank
        icono = "✅" if rank else "❌"
        pos = f"pos {rank}" if rank else "no recuperado"
        print(f"  {icono} [{pos:>13}] {c['pregunta'][:60]}")

    # --- Rechazo (casos fuera de alcance) ---
    rechazos_ok = 0
    print("\nCONTROL DE ALUCINACIÓN (deben rechazarse)")
    for c in fuera_alcance:
        frags = vectorstore.query(c["pregunta"], top_k=args.top_k)
        rel_max = max((f["relevancia"] for f in frags), default=0.0)
        rechazado = rel_max < settings.min_relevance
        if rechazado:
            rechazos_ok += 1
        icono = "✅" if rechazado else "❌"
        print(f"  {icono} [rel_max {rel_max:.2f}] {c['pregunta'][:60]}")

    # --- Resumen ---
    n = len(en_alcance)
    hit_at_k = hits / n if n else 0
    mrr = suma_rr / n if n else 0
    rechazo = rechazos_ok / len(fuera_alcance) if fuera_alcance else 0

    print("\n" + "=" * 50)
    print("RESUMEN")
    print(f"  Hit@{args.top_k}:          {hit_at_k:.1%}  ({hits}/{n})")
    print(f"  MRR:             {mrr:.3f}")
    print(f"  Rechazo correcto: {rechazo:.1%}  ({rechazos_ok}/{len(fuera_alcance)})")
    print("=" * 50)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
