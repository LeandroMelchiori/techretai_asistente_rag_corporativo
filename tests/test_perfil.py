"""
Tests de los perfiles de empresa: que cada perfil del repositorio sea válido y
coherente con sus documentos, que cambiar de empresa no afloje las reglas de
seguridad del prompt y que el público de clientes esté bien delimitado.
"""
import json
from pathlib import Path

import pytest

from src import agent
from src.config import BASE_DIR
from src.perfil import PerfilInvalido, cargar

PERFILES = sorted(p.parent for p in (BASE_DIR / "perfiles").glob("*/perfil.toml"))


def _escribir(tmp_path: Path, contenido: str) -> Path:
    (tmp_path / "perfil.toml").write_text(contenido, encoding="utf-8")
    return tmp_path


MINIMO = """
id = "demo"
[empresa]
nombre = "Demo S.A."
descripcion = "una empresa de prueba"
[asistente]
nombre = "DemoBot"
descripcion = "Asistente de Demo"
[empleados]
bienvenida = "Preguntá lo que quieras."
[categorias]
rrhh = "RR. HH."
clientes = "Clientes"
"""

CONECTOR = """
[conectores]
{nombre} = "{modo}"
"""

CLIENTES = """
[clientes]
bienvenida = "Consultá envíos y garantías."
categorias = {categorias}
"""


def test_hay_al_menos_un_perfil():
    assert "techretail" in {p.name for p in PERFILES}


@pytest.mark.parametrize("directorio", PERFILES, ids=lambda p: p.name)
def test_cada_perfil_es_valido_y_coherente_con_sus_documentos(directorio):
    perfil = cargar(directorio)

    assert perfil.coleccion == f"{perfil.id}_docs"
    assert perfil.sugerencias_para("empleado"), "la pantalla de inicio necesita preguntas sugeridas"
    if perfil.atiende_clientes:
        assert perfil.sugerencias_para("cliente")
    # Cada subcarpeta de documentos/ tiene un nombre visible, y las públicas existen.
    carpetas = {p.name for p in (directorio / "documentos").iterdir() if p.is_dir()}
    assert carpetas, "el perfil no tiene documentos"
    assert carpetas <= set(perfil.categorias), carpetas - set(perfil.categorias)
    assert set(perfil.categorias_publicas) <= carpetas
    # Y su set de evaluación sólo espera documentos que existen.
    casos = json.loads((directorio / "preguntas_eval.json").read_text(encoding="utf-8"))["casos"]
    existentes = {p.name for p in (directorio / "documentos").rglob("*") if p.is_file()}
    esperados = {f for c in casos for f in c["fuentes"]}
    assert esperados <= existentes, esperados - existentes
    # Los conectores en modo demo tienen sus datos de ejemplo.
    for conector, modo in perfil.conectores.items():
        if modo == "demo":
            assert (directorio / "demo" / f"{conector}.json").is_file()


@pytest.mark.parametrize("directorio", PERFILES, ids=lambda p: p.name)
def test_el_prompt_presenta_la_empresa_y_mantiene_las_reglas(directorio):
    perfil = cargar(directorio)

    for acceso in ("empleado", "cliente"):
        prompt = agent.system_prompt(perfil, acceso)
        assert perfil.asistente in prompt and perfil.empresa in prompt
        # Las reglas de seguridad no dependen del perfil ni del público.
        assert agent._REGLAS in prompt


def test_los_perfiles_no_comparten_coleccion():
    colecciones = [cargar(p).coleccion for p in PERFILES]
    assert len(colecciones) == len(set(colecciones))


def test_perfil_minimo_es_solo_interno(tmp_path):
    perfil = cargar(_escribir(tmp_path, MINIMO))

    assert perfil.resaltado == ""
    assert perfil.sugerencias == []
    assert perfil.conectores == {}
    assert perfil.atiende_clientes is False
    assert perfil.categoria("ventas") == "ventas"  # sin nombre visible, la clave


def test_publico_de_clientes(tmp_path):
    texto = MINIMO + CLIENTES.format(categorias='["clientes"]') + """
[[sugerencias]]
para = "clientes"
texto = "¿Cuánto tarda el envío?"

[[sugerencias]]
texto = "¿Cuántos días de vacaciones tengo?"
"""
    perfil = cargar(_escribir(tmp_path, texto))

    assert perfil.atiende_clientes and perfil.categorias_publicas == ["clientes"]
    assert perfil.bienvenida("cliente") == "Consultá envíos y garantías."
    assert perfil.bienvenida("empleado") == "Preguntá lo que quieras."
    assert [s.texto for s in perfil.sugerencias_para("cliente")] == ["¿Cuánto tarda el envío?"]
    # Sin "para", la sugerencia es para empleados.
    assert [s.texto for s in perfil.sugerencias_para("empleado")] == ["¿Cuántos días de vacaciones tengo?"]


@pytest.mark.parametrize("categorias, error", [
    ("[]", "no puede estar vacía"),
    ('["ventas"]', "categorías desconocidas: ventas"),
])
def test_publico_de_clientes_invalido(tmp_path, categorias, error):
    with pytest.raises(PerfilInvalido, match=error):
        cargar(_escribir(tmp_path, MINIMO + CLIENTES.format(categorias=categorias)))


def test_sugerencia_para_un_publico_desconocido(tmp_path):
    texto = MINIMO + '\n[[sugerencias]]\npara = "socios"\ntexto = "hola"\n'
    with pytest.raises(PerfilInvalido, match="para"):
        cargar(_escribir(tmp_path, texto))


def test_falta_un_campo_obligatorio(tmp_path):
    sin_nombre = MINIMO.replace('nombre = "Demo S.A."\n', "")
    with pytest.raises(PerfilInvalido, match=r"\[empresa\] nombre"):
        cargar(_escribir(tmp_path, sin_nombre))


@pytest.mark.parametrize("id_", ["demo/../x", "ñandú", "Demo", "_demo"])
def test_id_con_caracteres_invalidos(tmp_path, id_):
    with pytest.raises(PerfilInvalido, match="id"):
        cargar(_escribir(tmp_path, MINIMO.replace('id = "demo"', f'id = "{id_}"')))


def test_directorio_sin_perfil(tmp_path):
    with pytest.raises(PerfilInvalido, match="PERFIL"):
        cargar(tmp_path)


def test_conector_desconocido(tmp_path):
    with pytest.raises(PerfilInvalido, match="conector desconocido"):
        cargar(_escribir(tmp_path, MINIMO + CONECTOR.format(nombre="shopify", modo="demo")))


def test_modo_de_conector_no_disponible(tmp_path):
    with pytest.raises(PerfilInvalido, match="admite los modos: demo"):
        cargar(_escribir(tmp_path, MINIMO + CONECTOR.format(nombre="mercadolibre", modo="api")))
