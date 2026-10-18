"""
Tests del ciclo de herramientas con Gemini, con un cliente falso de google-genai
que devuelve respuestas armadas con los tipos reales de la librería.
"""
import pytest
from google.genai import types

from src import providers
from src.config import settings
from src.herramientas.base import SIN_PARAMETROS, Herramienta, Resultado


def _respuesta(*partes):
    return types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role="model", parts=list(partes)))]
    )


def _llamada(nombre, args=None):
    return types.Part(function_call=types.FunctionCall(name=nombre, args=args or {}))


class _ClienteFalso:
    """Devuelve una lista de respuestas por ronda y registra lo que recibe."""

    def __init__(self, rondas):
        self.rondas = list(rondas)
        self.recibido = []
        self.models = self

    def generate_content_stream(self, *, model, contents, config):
        self.recibido.append({"contents": list(contents), "config": config})
        if config.tool_config is not None:  # última ronda: sin herramientas
            return iter([_respuesta(types.Part.from_text(text="Respuesta forzada."))])
        return iter(self.rondas.pop(0))


HERRAMIENTA = Herramienta("ml_pedidos", "Pedidos.", SIN_PARAMETROS, lambda: Resultado({}), "Mercado Libre")


@pytest.fixture
def gemini(monkeypatch):
    monkeypatch.setattr(settings, "provider", "gemini")

    def instalar(rondas):
        cliente = _ClienteFalso(rondas)
        monkeypatch.setattr(providers, "_gemini", lambda: cliente)
        return cliente

    return instalar


def test_ejecuta_lo_que_pide_el_modelo_y_le_devuelve_el_resultado(gemini):
    cliente = gemini([
        [_respuesta(_llamada("ml_pedidos", {"estado": "demorado"}))],
        [_respuesta(types.Part.from_text(text="Hay un pedido ")), _respuesta(types.Part.from_text(text="demorado."))],
    ])
    ejecutadas = []

    def ejecutar(nombre, args):
        ejecutadas.append((nombre, args))
        return {"total": 1}

    texto = "".join(providers.generate_con_herramientas("sistema", "pregunta", [HERRAMIENTA], ejecutar))

    assert texto == "Hay un pedido demorado."
    assert ejecutadas == [("ml_pedidos", {"estado": "demorado"})]
    # En la segunda ronda el modelo recibe su llamada y la respuesta de la herramienta.
    historial = cliente.recibido[1]["contents"]
    assert historial[1].role == "model" and historial[1].parts[0].function_call.name == "ml_pedidos"
    respuesta = historial[2].parts[0].function_response
    assert respuesta.name == "ml_pedidos" and respuesta.response == {"total": 1}
    # Las llamadas las ejecuta el agente, no la librería.
    assert cliente.recibido[0]["config"].automatic_function_calling.disable is True


def test_varias_llamadas_en_la_misma_ronda(gemini):
    gemini([
        [_respuesta(_llamada("ml_pedidos"), _llamada("ml_pedidos", {"estado": "entregado"}))],
        [_respuesta(types.Part.from_text(text="Listo."))],
    ])
    ejecutadas = []

    def ejecutar(nombre, args):
        ejecutadas.append(args)
        return {}

    assert "".join(providers.generate_con_herramientas("s", "p", [HERRAMIENTA], ejecutar)) == "Listo."
    assert ejecutadas == [{}, {"estado": "entregado"}]


def test_despues_de_max_rondas_el_modelo_tiene_que_responder(gemini):
    # El modelo pediría herramientas para siempre.
    cliente = gemini([[_respuesta(_llamada("ml_pedidos"))] for _ in range(10)])

    texto = "".join(providers.generate_con_herramientas("s", "p", [HERRAMIENTA], lambda n, a: {}, max_rondas=2))

    assert texto == "Respuesta forzada."
    assert len(cliente.recibido) == 3
    ultima = cliente.recibido[-1]["config"]
    assert ultima.tool_config.function_calling_config.mode == types.FunctionCallingConfigMode.NONE


def test_no_muestra_el_razonamiento_interno(gemini):
    gemini([[_respuesta(types.Part(text="pensando...", thought=True), types.Part.from_text(text="Respuesta."))]])

    assert "".join(providers.generate_con_herramientas("s", "p", [HERRAMIENTA], lambda n, a: {})) == "Respuesta."


def test_con_openai_las_herramientas_no_estan_disponibles(monkeypatch):
    monkeypatch.setattr(settings, "provider", "openai")
    with pytest.raises(RuntimeError, match="Gemini"):
        providers.generate_con_herramientas("s", "p", [HERRAMIENTA], lambda n, a: {})
