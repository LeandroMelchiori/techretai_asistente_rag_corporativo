"""
Tests de los perfiles de empresa: que cada perfil del repositorio sea válido y
coherente con sus documentos, y que cambiar de empresa no afloje las reglas de
seguridad del prompt.
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
bienvenida = "Preguntá lo que quieras."
"""

CONECTOR = """
[conectores]
{nombre} = "{modo}"
"""


def test_hay_al_menos_dos_perfiles():
    assert {p.name for p in PERFILES} >= {"techretail", "nogal"}


@pytest.mark.parametrize("directorio", PERFILES, ids=lambda p: p.name)
def test_cada_perfil_es_valido_y_coherente_con_sus_documentos(directorio):
    perfil = cargar(directorio)

    assert perfil.coleccion == f"{perfil.id}_docs"
    assert perfil.sugerencias, "la pantalla de inicio necesita preguntas sugeridas"
    # Cada subcarpeta de documentos/ tiene un nombre visible.
    carpetas = {p.name for p in (directorio / "documentos").iterdir() if p.is_dir()}
    assert carpetas, "el perfil no tiene documentos"
    assert carpetas <= set(perfil.categorias), carpetas - set(perfil.categorias)
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
    prompt = agent.system_prompt(perfil)

    assert perfil.asistente in prompt and perfil.empresa in prompt
    # Las reglas de seguridad no dependen del perfil.
    assert agent._REGLAS in prompt
    assert "no confiables" in prompt.lower()


def test_los_perfiles_no_comparten_coleccion():
    colecciones = [cargar(p).coleccion for p in PERFILES]
    assert len(colecciones) == len(set(colecciones))


def test_perfil_minimo_usa_valores_por_defecto(tmp_path):
    perfil = cargar(_escribir(tmp_path, MINIMO))

    assert perfil.resaltado == ""
    assert perfil.sugerencias == []
    assert perfil.categoria("rrhh") == "rrhh"  # sin nombre visible, la clave


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


def test_sin_conectores_el_perfil_no_usa_el_agente(tmp_path):
    assert cargar(_escribir(tmp_path, MINIMO)).conectores == {}
