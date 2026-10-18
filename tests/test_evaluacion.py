"""Tests de la verificación que usa la evaluación del agente."""
import json

from eval.evaluar_agente import verificar
from src import agent
from src.config import BASE_DIR
from src.perfil import cargar

CASO = {
    "herramientas": ["ml_preguntas_sin_responder"],
    "debe_mencionar": [["4 preguntas", "cuatro preguntas"], ["espejo"]],
    "no_debe_mencionar": ["canberra"],
}


def test_un_caso_correcto_no_tiene_problemas():
    texto = "Tenés cuatro preguntas. La del ESPEJO parece sospechosa."
    assert verificar(CASO, texto, ["ml_preguntas_sin_responder"]) == []


def test_detecta_herramienta_faltante_mencion_faltante_y_prohibida():
    problemas = verificar(CASO, "Tenés 3 preguntas. Canberra.", [])

    assert "no usó ml_preguntas_sin_responder" in problemas
    assert "no menciona 4 preguntas / cuatro preguntas" in problemas
    assert "no menciona espejo" in problemas
    assert "menciona 'canberra'" in problemas


def test_ignora_tildes_y_mayusculas():
    caso = {"herramientas": [], "debe_mencionar": [["ultima unidad"]], "no_debe_mencionar": []}
    assert verificar(caso, "Queda la Última unidad.", []) == []


def test_los_casos_de_nogal_usan_herramientas_que_existen():
    nogal = cargar(BASE_DIR / "perfiles" / "nogal")
    disponibles = {h.nombre for h in agent.herramientas_de(nogal)}
    casos = json.loads((nogal.directorio / "casos_agente.json").read_text(encoding="utf-8"))["casos"]

    for caso in casos:
        assert set(caso["herramientas"]) <= disponibles, caso["id"]
