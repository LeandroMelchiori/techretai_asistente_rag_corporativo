"""
Tests de la sincronización del índice con la carpeta de documentos.

Usan una base Chroma real en un directorio temporal; sólo se simulan los
embeddings (sin llamadas a la API) y la división en fragmentos, que acá es un
fragmento por párrafo para controlar cuántos genera cada documento.
"""
import io
import tarfile

import pytest

from scripts import ingest
from src import vectorstore
from src.config import settings
from src.ingestion import indexar


@pytest.fixture
def embebidos(tmp_path, monkeypatch):
    """Índice vacío en tmp_path; devuelve la lista de textos que se embebieron."""
    monkeypatch.setattr(settings, "chroma_dir", tmp_path / "chroma")
    textos = []

    def embed_falso(lote, is_query=False):
        textos.extend(lote)
        return [[float(len(t)), 1.0, 0.5] for t in lote]

    monkeypatch.setattr(vectorstore, "embed_texts", embed_falso)
    monkeypatch.setattr(indexar, "dividir_en_chunks", lambda texto: [p for p in texto.split("\n\n") if p])
    return textos


@pytest.fixture
def docs(tmp_path):
    carpeta = tmp_path / "docs"
    (carpeta / "rrhh").mkdir(parents=True)
    (carpeta / "legal").mkdir()
    (carpeta / "rrhh" / "vacaciones.md").write_text("Uno.\n\nDos.\n\nTres.", encoding="utf-8")
    (carpeta / "legal" / "privacidad.md").write_text("Datos personales.", encoding="utf-8")
    return carpeta


def _fragmentos(ruta):
    return sorted(vectorstore.get_collection().get(where={"ruta": ruta})["documents"])


def _sincronizar(carpeta):
    return indexar.sincronizar(carpeta, avisar=lambda _: None)


def test_indexa_los_nuevos_y_saltea_los_que_no_cambiaron(docs, embebidos):
    r = _sincronizar(docs)
    assert sorted(r.nuevos) == ["legal/privacidad.md", "rrhh/vacaciones.md"]
    assert r.fragmentos == 4
    assert _fragmentos("rrhh/vacaciones.md") == ["Dos.", "Tres.", "Uno."]

    embebidos.clear()
    r = _sincronizar(docs)
    assert sorted(r.sin_cambios) == ["legal/privacidad.md", "rrhh/vacaciones.md"]
    assert embebidos == []  # sin cambios no se vuelve a llamar a la API


def test_un_documento_modificado_reemplaza_sus_fragmentos(docs, embebidos):
    _sincronizar(docs)

    # Mismo número de fragmentos, otro contenido: antes quedaba el texto viejo.
    (docs / "legal" / "privacidad.md").write_text("Datos personales actualizados.", encoding="utf-8")
    # Menos fragmentos: no deben quedar los que sobran de la versión anterior.
    (docs / "rrhh" / "vacaciones.md").write_text("Veintiún días.", encoding="utf-8")
    r = _sincronizar(docs)

    assert sorted(r.actualizados) == ["legal/privacidad.md", "rrhh/vacaciones.md"]
    assert _fragmentos("legal/privacidad.md") == ["Datos personales actualizados."]
    assert _fragmentos("rrhh/vacaciones.md") == ["Veintiún días."]
    assert vectorstore.stats()["fragmentos"] == 2


def test_un_documento_borrado_se_quita_del_indice(docs, embebidos):
    _sincronizar(docs)
    (docs / "legal" / "privacidad.md").unlink()

    r = _sincronizar(docs)

    assert r.quitados == ["legal/privacidad.md"]
    assert _fragmentos("legal/privacidad.md") == []
    assert set(vectorstore.firmas_indexadas()) == {"rrhh/vacaciones.md"}


def test_si_falla_la_extraccion_queda_la_version_anterior(docs, embebidos, monkeypatch):
    _sincronizar(docs)
    (docs / "rrhh" / "vacaciones.md").write_text("Versión nueva.", encoding="utf-8")

    def extraccion_rota(archivo):
        raise ValueError("archivo dañado")

    monkeypatch.setattr(indexar, "extract_text", extraccion_rota)
    r = _sincronizar(docs)

    assert "rrhh/vacaciones.md" in r.con_error
    assert _fragmentos("rrhh/vacaciones.md") == ["Dos.", "Tres.", "Uno."]


def test_si_falla_la_api_de_embeddings_queda_la_version_anterior(docs, embebidos, monkeypatch):
    _sincronizar(docs)
    (docs / "rrhh" / "vacaciones.md").write_text("Versión nueva.", encoding="utf-8")

    def cuota_agotada(lote, is_query=False):
        raise RuntimeError("429: cuota agotada")

    monkeypatch.setattr(vectorstore, "embed_texts", cuota_agotada)
    with pytest.raises(RuntimeError):
        _sincronizar(docs)

    assert _fragmentos("rrhh/vacaciones.md") == ["Dos.", "Tres.", "Uno."]


def test_cambiar_el_modelo_de_embeddings_reindexa_todo(docs, embebidos, monkeypatch):
    _sincronizar(docs)
    monkeypatch.setattr(settings, "gemini_embed_model", "otro-modelo")

    r = _sincronizar(docs)

    assert sorted(r.actualizados) == ["legal/privacidad.md", "rrhh/vacaciones.md"]


def test_la_categoria_es_la_primera_subcarpeta():
    assert indexar.categoria_de("rrhh/politicas/vacaciones.md") == "rrhh"
    assert indexar.categoria_de("suelto.md") == "general"


# --- scripts/ingest.py ---------------------------------------------------------

def _tar(miembros):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tar:
        for nombre, contenido in miembros.items():
            info = tarfile.TarInfo(nombre)
            info.size = len(contenido)
            tar.addfile(info, io.BytesIO(contenido))
    buffer.seek(0)
    return buffer


def test_una_carpeta_vacia_no_vacia_el_indice(docs, embebidos, tmp_path):
    _sincronizar(docs)
    vacia = tmp_path / "vacia"
    vacia.mkdir()

    assert ingest._indexar(vacia, reset=False) == 1
    assert vectorstore.stats()["fragmentos"] == 4


def test_extrae_el_tar_con_la_carpeta_documentos(tmp_path):
    flujo = _tar({"documentos/rrhh/vacaciones.md": b"Uno."})

    carpeta = ingest._extraer_tar(flujo, tmp_path)

    assert carpeta == tmp_path / "documentos"
    assert (carpeta / "rrhh" / "vacaciones.md").read_text(encoding="utf-8") == "Uno."


def test_el_tar_no_puede_escribir_fuera_del_directorio_temporal(tmp_path):
    flujo = _tar({"../fuera.md": b"no"})

    with pytest.raises(tarfile.TarError):
        ingest._extraer_tar(flujo, tmp_path / "destino")
    assert not (tmp_path / "fuera.md").exists()


# --- Filtro por categorías (acceso de clientes) ---------------------------------

def test_la_busqueda_por_categorias_nunca_devuelve_otras(docs, embebidos):
    (docs / "clientes").mkdir()
    (docs / "clientes" / "envios.md").write_text("Envíos a todo el país.", encoding="utf-8")
    _sincronizar(docs)

    publicos = vectorstore.query("vacaciones", top_k=10, categorias=["clientes"])
    assert {f["meta"]["categoria"] for f in publicos} == {"clientes"}
    # Sin filtro se recupera todo.
    assert {f["meta"]["categoria"] for f in vectorstore.query("x", top_k=10)} == {"clientes", "rrhh", "legal"}
    # Pedir una categoría fuera de las permitidas no devuelve nada.
    assert vectorstore.query("x", categoria="rrhh", categorias=["clientes"]) == []
