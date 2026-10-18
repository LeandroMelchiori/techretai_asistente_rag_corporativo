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

Con ``--acceso cliente`` se busca sólo en las categorías públicas: Hit@k y MRR
se miden sobre las preguntas públicas, y para las internas se cuenta si se
recuperó algún documento interno (tiene que ser cero).

Requisitos: haber indexado los documentos (`python -m scripts.ingest`)
y tener la API key configurada.

Uso:
    python -m eval.evaluar
    python -m eval.evaluar --top-k 5
    python -m eval.evaluar --acceso cliente
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import vectorstore  # noqa: E402
from src.config import settings  # noqa: E402
from src.ingestion.indexar import categoria_de, documentos_en  # noqa: E402
from src.perfil import perfil_activo  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Evalúa la recuperación del agente.")
    parser.add_argument("--top-k", type=int, default=settings.top_k)
    parser.add_argument("--acceso", choices=["empleado", "cliente"], default="empleado")
    parser.add_argument(
        "--casos", type=Path, default=settings.perfil_dir / "preguntas_eval.json",
        help="Set de evaluación (por defecto, el del perfil activo).",
    )
    args = parser.parse_args()

    settings.validate()
    perfil = perfil_activo()
    if vectorstore.stats()["fragmentos"] == 0:
        print("La base vectorial está vacía. Corré primero: python -m scripts.ingest")
        return 1
    publicas = perfil.categorias_publicas if args.acceso == "cliente" else None
    if args.acceso == "cliente" and not publicas:
        print(f"El perfil '{perfil.id}' no tiene información para clientes.")
        return 1

    # Documento -> categoría, para saber qué es público.
    categoria = {Path(r).name: categoria_de(r) for r in documentos_en(settings.docs_dir)}

    def es_publico(archivo: str) -> bool:
        return publicas is None or categoria.get(archivo) in publicas

    casos = json.loads(args.casos.read_text(encoding="utf-8"))["casos"]
    en_alcance = [c for c in casos if c["fuentes"] and all(es_publico(f) for f in c["fuentes"])]
    internas = [c for c in casos if c["fuentes"] and not all(es_publico(f) for f in c["fuentes"])]
    fuera_alcance = [c for c in casos if not c["fuentes"]]

    def recuperar(pregunta: str):
        return vectorstore.query(pregunta, top_k=args.top_k, categorias=publicas)

    print(f"Evaluando {len(casos)} casos (top_k={args.top_k}, acceso={args.acceso})\n")

    # --- Recuperación (casos en alcance) ---
    hits = 0
    suma_rr = 0.0
    print("RECUPERACIÓN")
    for c in en_alcance:
        recuperados = [f["meta"]["archivo"] for f in recuperar(c["pregunta"])]
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

    # --- Aislamiento (modo cliente: preguntas sobre información interna) ---
    fugas = 0
    if internas:
        print("\nAISLAMIENTO (preguntas internas en modo cliente: ningún documento interno)")
        for c in internas:
            filtrados = [f["meta"]["archivo"] for f in recuperar(c["pregunta"])
                         if not es_publico(f["meta"]["archivo"])]
            fugas += bool(filtrados)
            icono = "❌" if filtrados else "✅"
            print(f"  {icono} {c['pregunta'][:60]}" + (f" -> {filtrados}" if filtrados else ""))

    # --- Rechazo (casos fuera de alcance) ---
    rechazos_ok = 0
    print("\nCONTROL DE ALUCINACIÓN (deben rechazarse)")
    for c in fuera_alcance:
        rel_max = max((f["relevancia"] for f in recuperar(c["pregunta"])), default=0.0)
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
    if internas:
        print(f"  Documentos internos recuperados: {fugas}/{len(internas)} preguntas internas")
    print("=" * 50)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
