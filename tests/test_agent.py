"""
Tests del agente: control de alucinación (fallback) y citación de fuentes.

Se simulan la recuperación (``vectorstore.query``) y la generación
(``generate``) para probar la lógica sin llamar a servicios externos.
"""
from src import agent


def _frag(archivo, categoria, relevancia):
    return {
        "texto": f"Contenido de {archivo}.",
        "meta": {"archivo": archivo, "categoria": categoria, "formato": "md"},
        "relevancia": relevancia,
    }


def test_fallback_cuando_nada_supera_el_umbral(monkeypatch):
    # Todos los fragmentos por debajo del umbral -> no debe generar respuesta.
    monkeypatch.setattr(agent.vectorstore, "query", lambda *a, **k: [_frag("x.md", "rrhh", 0.05)])
    monkeypatch.setattr(agent, "generate", lambda s, u: "ESTO NO DEBERÍA DEVOLVERSE")

    r = agent.responder("pregunta sin relación con los documentos")

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

    monkeypatch.setattr(agent, "generate", fake_generate)

    r = agent.responder("¿cuántos días de vacaciones tengo?")

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
    monkeypatch.setattr(agent, "generate", lambda s, u: "ok")

    r = agent.responder("una pregunta cualquiera")

    archivos = [f["archivo"] for f in r.fuentes]
    assert archivos.count("a.md") == 1  # deduplicado
    assert "b.md" in archivos


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

    monkeypatch.setattr(agent, "generate", fake_generate)

    r = agent.responder("¿cuántos días de vacaciones tengo?")

    archivos = [f["archivo"] for f in r.fuentes]
    assert archivos == ["vacaciones.docx", "beneficios.html"]
    assert "planes_y_precios.xlsx" not in capturado["user"]
