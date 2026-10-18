"""
Tests del agente: control de alucinación (fallback) y citación de fuentes.

Se simulan la recuperación (``vectorstore.query``) y la generación
(``generate_stream``) para probar la lógica sin llamar a servicios externos.
Se usa el perfil de TechRetail sin conectores: el RAG directo, sin el agente.
"""
from dataclasses import replace

import pytest

from src import agent
from src.perfil import perfil_activo

RAG = replace(perfil_activo(), conectores={})


def _stream(funcion):
    """Adapta un generate(system, user) -> str simulado a generate_stream."""
    return lambda s, u: iter([funcion(s, u)])


def _frag(archivo, categoria, relevancia):
    return {
        "texto": f"Contenido de {archivo}.",
        "meta": {"archivo": archivo, "categoria": categoria, "formato": "md"},
        "relevancia": relevancia,
    }


def test_fallback_cuando_nada_supera_el_umbral(monkeypatch):
    # Todos los fragmentos por debajo del umbral -> no debe generar respuesta.
    monkeypatch.setattr(agent.vectorstore, "query", lambda *a, **k: [_frag("x.md", "rrhh", 0.05)])
    monkeypatch.setattr(agent, "generate_stream", _stream(lambda s, u: "ESTO NO DEBERÍA DEVOLVERSE"))

    r = agent.responder("pregunta sin relación con los documentos", perfil=RAG)

    assert r.contexto_encontrado is False
    assert "no encontré" in r.texto.lower()
    assert r.fuentes == []


def test_responde_usando_el_contexto(monkeypatch):
    monkeypatch.setattr(
        agent.vectorstore, "query", lambda *a, **k: [_frag("vacaciones.docx", "rrhh", 0.82)]
    )
    capturado = {}

    def fake_generate(system_prompt, user_prompt):
        capturado["user"] = user_prompt
        return "Te corresponden 21 días."

    monkeypatch.setattr(agent, "generate_stream", _stream(fake_generate))

    r = agent.responder("¿cuántos días de vacaciones tengo?", perfil=RAG)

    assert r.contexto_encontrado is True
    assert r.texto == "Te corresponden 21 días."
    assert any(f["archivo"] == "vacaciones.docx" for f in r.fuentes)
    # El contexto que recibe el LLM debe incluir el nombre del documento fuente.
    assert "vacaciones.docx" in capturado["user"]


def test_fuentes_sin_duplicados(monkeypatch):
    frags = [
        _frag("a.md", "rrhh", 0.7),
        _frag("a.md", "rrhh", 0.68),  # mismo documento repetido
        _frag("b.md", "legal", 0.66),
    ]
    monkeypatch.setattr(agent.vectorstore, "query", lambda *a, **k: frags)
    monkeypatch.setattr(agent, "generate_stream", _stream(lambda s, u: "ok"))

    r = agent.responder("una pregunta cualquiera", perfil=RAG)

    archivos = [f["archivo"] for f in r.fuentes]
    assert archivos.count("a.md") == 1  # deduplicado
    assert "b.md" in archivos


def test_responder_en_vivo_entrega_partes_y_completa_la_respuesta(monkeypatch):
    monkeypatch.setattr(
        agent.vectorstore, "query", lambda *a, **k: [_frag("vacaciones.docx", "rrhh", 0.82)]
    )
    monkeypatch.setattr(agent, "generate_stream", lambda s, u: iter(["Te corresponden ", "21 días."]))

    resp, partes = agent.responder_en_vivo("¿cuántos días de vacaciones tengo?", perfil=RAG)

    # Las fuentes están disponibles antes de generar el texto.
    assert [f["archivo"] for f in resp.fuentes] == ["vacaciones.docx"]
    assert resp.texto == ""
    assert list(partes) == ["Te corresponden ", "21 días."]
    assert resp.texto == "Te corresponden 21 días."
    assert resp.contexto_encontrado is True


def test_responder_en_vivo_sin_contexto_no_llama_al_llm(monkeypatch):
    monkeypatch.setattr(agent.vectorstore, "query", lambda *a, **k: [_frag("x.md", "rrhh", 0.05)])

    def no_deberia_llamarse(s, u):
        raise AssertionError("no debe generar sin contexto")

    monkeypatch.setattr(agent, "generate_stream", no_deberia_llamarse)

    resp, partes = agent.responder_en_vivo("pregunta sin relación", perfil=RAG)

    assert "".join(partes) == agent.FALLBACK
    assert resp.texto == agent.FALLBACK
    assert resp.contexto_encontrado is False
    assert resp.fuentes == []


def test_descarta_fuentes_lejos_del_mejor_resultado(monkeypatch):
    # Superan el umbral absoluto, pero quedan muy por debajo del mejor: no se citan
    # ni llegan al contexto del LLM.
    frags = [
        _frag("vacaciones.docx", "rrhh", 0.70),
        _frag("beneficios.html", "rrhh", 0.64),
        _frag("planes_y_precios.xlsx", "comercial", 0.55),
    ]
    monkeypatch.setattr(agent.vectorstore, "query", lambda *a, **k: frags)
    capturado = {}

    def fake_generate(system_prompt, user_prompt):
        capturado["user"] = user_prompt
        return "ok"

    monkeypatch.setattr(agent, "generate_stream", _stream(fake_generate))

    r = agent.responder("¿cuántos días de vacaciones tengo?", perfil=RAG)

    archivos = [f["archivo"] for f in r.fuentes]
    assert archivos == ["vacaciones.docx", "beneficios.html"]
    assert "planes_y_precios.xlsx" not in capturado["user"]


# --- Modo cliente --------------------------------------------------------------
def test_un_cliente_solo_busca_en_las_categorias_publicas(monkeypatch):
    perfil = perfil_activo()
    recibido = {}

    def query(*a, **k):
        recibido.update(k)
        return [_frag("garantia.html", "clientes", 0.8)]

    def no_deberia_llamarse(*a, **k):
        raise AssertionError("un cliente nunca usa el agente ni sus herramientas")

    monkeypatch.setattr(agent.vectorstore, "query", query)
    monkeypatch.setattr(agent, "generate_con_herramientas", no_deberia_llamarse)
    capturado = {}

    def generar(system_prompt, user_prompt):
        capturado["system"], capturado["user"] = system_prompt, user_prompt
        return iter(["Doce meses."])

    monkeypatch.setattr(agent, "generate_stream", generar)

    resp, partes = agent.responder_en_vivo("¿garantía?", perfil=perfil, acceso="cliente")

    assert "".join(partes) == "Doce meses."
    assert recibido["categorias"] == perfil.categorias_publicas
    assert resp.acceso == "cliente" and resp.consultas == []
    assert "atención al cliente" in capturado["system"]
    assert "PREGUNTA DEL CLIENTE" in capturado["user"]


def test_un_perfil_sin_publico_de_clientes_no_atiende_clientes():
    with pytest.raises(ValueError, match="clientes"):
        agent.responder_en_vivo("hola", perfil=replace(RAG, categorias_publicas=[]), acceso="cliente")


def test_el_rag_directo_cuenta_una_llamada_al_modelo(monkeypatch):
    monkeypatch.setattr(agent.vectorstore, "query", lambda *a, **k: [_frag("a.md", "rrhh", 0.8)])
    monkeypatch.setattr(agent, "generate_stream", lambda s, u: iter(["ok"]))

    assert agent.responder("x", perfil=RAG).llamadas_modelo == 1


def test_sin_contexto_no_hay_llamadas_al_modelo(monkeypatch):
    monkeypatch.setattr(agent.vectorstore, "query", lambda *a, **k: [])

    assert agent.responder("x", perfil=RAG).llamadas_modelo == 0


def test_si_el_modelo_no_encuentra_la_respuesta_no_se_citan_fuentes(monkeypatch):
    # Los fragmentos superan el umbral, pero el modelo decide que no responden la pregunta.
    monkeypatch.setattr(agent.vectorstore, "query", lambda *a, **k: [_frag("envios.md", "clientes", 0.56)])
    monkeypatch.setattr(
        agent, "generate_stream",
        lambda s, u: iter(["No encontré esta información en los documentos disponibles."]),
    )

    r = agent.responder("¿Qué tiempo va a hacer mañana?", perfil=RAG)

    assert r.fuentes == []
    assert r.contexto_encontrado is False
