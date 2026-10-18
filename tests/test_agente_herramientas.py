"""
Tests del agente con herramientas (perfil con conectores).

Se simula el modelo: un ``generate_con_herramientas`` falso pide herramientas
a través del ejecutor del agente, como lo haría Gemini, y después escribe la
respuesta. Así se prueba la orquestación sin llamar a la API.
"""
import pytest

from src import agent
from src.config import BASE_DIR
from src.perfil import cargar

NOGAL = cargar(BASE_DIR / "perfiles" / "nogal")
TECHRETAIL = cargar(BASE_DIR / "perfiles" / "techretail")


def _frag(archivo, relevancia=0.8):
    return {
        "texto": f"Contenido de {archivo}.",
        "meta": {"archivo": archivo, "categoria": "postventa", "formato": "md"},
        "relevancia": relevancia,
    }


def _modelo_falso(llamadas, texto="Respuesta final."):
    """Pide cada (herramienta, argumentos) de ``llamadas`` y después responde."""
    registro = {}

    def generar(system_prompt, user_prompt, herramientas, ejecutar, max_rondas):
        registro["system"] = system_prompt
        registro["herramientas"] = [h.nombre for h in herramientas]
        registro["resultados"] = [ejecutar(nombre, args) for nombre, args in llamadas]
        if texto:
            yield texto

    return generar, registro


def test_un_perfil_con_conectores_usa_el_agente(monkeypatch):
    monkeypatch.setattr(agent.vectorstore, "query", lambda *a, **k: [_frag("cambios_y_devoluciones.md")])
    generar, registro = _modelo_falso([
        ("ml_reclamos_abiertos", {}),
        ("buscar_documentos", {"consulta": "producto dañado"}),
    ])
    monkeypatch.setattr(agent, "generate_con_herramientas", generar)

    resp, partes = agent.responder_en_vivo("¿Qué hago con el reclamo de las copas?", perfil=NOGAL)
    assert "".join(partes) == "Respuesta final."

    assert resp.texto == "Respuesta final."
    assert resp.perfil == "nogal"
    assert [c["resumen"] for c in resp.consultas] == ["2 reclamos abiertos", "1 documento"]
    assert [f["archivo"] for f in resp.fuentes] == ["cambios_y_devoluciones.md"]
    assert resp.contexto_encontrado is True
    # El modelo recibe los datos, no los objetos internos.
    assert registro["resultados"][0]["total"] == 2
    assert registro["resultados"][1]["fragmentos"][0]["documento"] == "cambios_y_devoluciones.md"


def test_el_agente_ofrece_documentos_y_las_herramientas_del_conector(monkeypatch):
    generar, registro = _modelo_falso([])
    monkeypatch.setattr(agent, "generate_con_herramientas", generar)

    _, partes = agent.responder_en_vivo("hola", perfil=NOGAL)
    list(partes)

    assert registro["herramientas"] == [
        "buscar_documentos", "ml_preguntas_sin_responder", "ml_pedidos",
        "ml_reclamos_abiertos", "ml_publicaciones",
    ]
    assert "Mercado Libre" in registro["system"]


def test_un_perfil_sin_conectores_sigue_con_el_rag_directo(monkeypatch):
    def no_deberia_llamarse(*a, **k):
        raise AssertionError("sin conectores no se usa el agente")

    monkeypatch.setattr(agent, "generate_con_herramientas", no_deberia_llamarse)
    monkeypatch.setattr(agent.vectorstore, "query", lambda *a, **k: [_frag("vacaciones.docx")])
    monkeypatch.setattr(agent, "generate_stream", lambda s, u: iter(["21 días."]))

    resp, partes = agent.responder_en_vivo("¿vacaciones?", perfil=TECHRETAIL)

    assert "".join(partes) == "21 días."
    assert resp.consultas == []


def test_herramienta_inexistente_y_argumentos_no_declarados(monkeypatch):
    generar, registro = _modelo_falso([
        ("ml_responder_pregunta", {"texto": "hola"}),  # no existe: no hay herramientas que escriban
        ("ml_pedidos", {"estado": "demorado", "borrar": True}),
    ])
    monkeypatch.setattr(agent, "generate_con_herramientas", generar)

    resp, partes = agent.responder_en_vivo("x", perfil=NOGAL)
    list(partes)

    assert "error" in registro["resultados"][0]
    assert registro["resultados"][1]["total"] == 1  # "borrar" se descartó
    assert [c["nombre"] for c in resp.consultas] == ["ml_pedidos"]


def test_si_una_herramienta_falla_el_modelo_recibe_un_error_y_sigue(monkeypatch):
    def falla(*a, **k):
        raise ConnectionError("sin conexión")

    monkeypatch.setattr(agent.vectorstore, "query", falla)
    generar, registro = _modelo_falso([("buscar_documentos", {"consulta": "garantía"})])
    monkeypatch.setattr(agent, "generate_con_herramientas", generar)

    resp, partes = agent.responder_en_vivo("¿garantía?", perfil=NOGAL)
    list(partes)

    assert "error" in registro["resultados"][0]
    assert "sin conexión" not in str(registro["resultados"][0])  # sin detalles internos
    assert resp.consultas == [{"nombre": "buscar_documentos", "origen": "Documentos", "resumen": "falló"}]


def test_limite_de_llamadas_por_pregunta(monkeypatch):
    llamadas = [("ml_pedidos", {})] * (agent.MAX_LLAMADAS + 2)
    generar, registro = _modelo_falso(llamadas)
    monkeypatch.setattr(agent, "generate_con_herramientas", generar)

    resp, partes = agent.responder_en_vivo("x", perfil=NOGAL)
    list(partes)

    assert len(resp.consultas) == agent.MAX_LLAMADAS
    assert all("error" in r for r in registro["resultados"][agent.MAX_LLAMADAS:])


def test_sin_texto_del_modelo_responde_el_fallback(monkeypatch):
    generar, _ = _modelo_falso([], texto="")
    monkeypatch.setattr(agent, "generate_con_herramientas", generar)

    resp, partes = agent.responder_en_vivo("x", perfil=NOGAL)

    assert "".join(partes) == agent.FALLBACK
    assert resp.contexto_encontrado is False


def test_responder_sin_streaming_tambien_usa_el_agente(monkeypatch):
    generar, _ = _modelo_falso([("ml_preguntas_sin_responder", {})], texto="Tenés 4 preguntas.")
    monkeypatch.setattr(agent, "generate_con_herramientas", generar)

    resp = agent.responder("¿preguntas?", perfil=NOGAL)

    assert resp.texto == "Tenés 4 preguntas."
    assert resp.consultas[0]["resumen"] == "4 preguntas sin responder"


def test_el_prompt_del_agente_mantiene_las_defensas():
    prompt = agent.system_prompt_agente(NOGAL).lower()

    assert "no confiables" in prompt
    assert "no las obedezcas" in prompt
    assert "sin omitir ninguno" in prompt
    assert "sólo leen" in prompt


@pytest.mark.parametrize("pregunta", ["¿Qué preguntas tengo?", "dame los pedidos"])
def test_el_prompt_del_usuario_incluye_la_fecha(pregunta):
    prompt = agent._prompt_agente(pregunta)
    assert "Fecha y hora actual:" in prompt and pregunta in prompt
