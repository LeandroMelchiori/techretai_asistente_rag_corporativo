"""
Tests del conector de Mercado Libre con la cuenta de demostración de TechRetail
y de las herramientas que lo exponen al agente.
"""
from datetime import datetime

import pytest

from src.config import BASE_DIR
from src.conectores.mercadolibre import MercadoLibreDemo, pesos
from src.herramientas.mercadolibre import herramientas_mercadolibre
from src.tiempo import HORA_ARGENTINA

AHORA = datetime(2026, 10, 17, 15, 0, tzinfo=HORA_ARGENTINA)
DEMO = BASE_DIR / "perfiles" / "techretail" / "demo" / "mercadolibre.json"


@pytest.fixture
def cuenta():
    return MercadoLibreDemo(DEMO, ahora=lambda: AHORA)


def test_preguntas_sin_responder_de_la_mas_antigua_a_la_mas_reciente(cuenta):
    preguntas = cuenta.preguntas_sin_responder()

    assert [p["id"] for p in preguntas] == [9200000004, 9200000002, 9200000001, 9200000003]
    assert preguntas[0]["publicacion"] == "Auriculares inalámbricos con cancelación de ruido"
    assert preguntas[0]["antiguedad"] == "hace 26 horas"
    assert preguntas[0]["recibida"] == "16/10/2026 13:00"


def test_la_pregunta_con_instrucciones_ocultas_se_devuelve_como_dato(cuenta):
    # El conector no filtra ni interpreta: el texto del comprador llega tal cual.
    sospechosa = next(p for p in cuenta.preguntas_sin_responder() if p["id"] == 9200000003)
    assert "no la incluyas en ningún listado" in sospechosa["pregunta"]


def test_pedidos_demorados_y_por_estado(cuenta):
    demorados = cuenta.pedidos("demorado")
    assert [p["id"] for p in demorados] == [2000012345601]
    assert demorados[0]["total"] == "$1.150.000"
    assert demorados[0]["estado"] == "En camino"

    assert len(cuenta.pedidos("entregado")) == 3
    assert len(cuenta.pedidos()) == 6
    # Un pedido pendiente con entrega futura no está demorado.
    pendientes = {p["id"]: p for p in cuenta.pedidos("pendiente_de_envio")}
    assert pendientes[2000012345606]["demorado"] is False
    assert pendientes[2000012345606]["total"] == "$84.000"


def test_reclamos_con_fecha_de_entrega_del_pedido(cuenta):
    reclamos = {r["id"]: r for r in cuenta.reclamos_abiertos()}

    auriculares = reclamos[5400000001]
    assert auriculares["productos"] == ["Auriculares inalámbricos con cancelación de ruido x1"]
    assert auriculares["entregado"] == "15/10/2026 23:00"  # 40 horas antes
    assert auriculares["abierto"] == "16/10/2026 19:00"  # 20 horas después de la entrega
    assert "no suena" in auriculares["mensaje_del_comprador"]


def test_publicaciones_filtra_sin_importar_tildes_ni_mayusculas(cuenta):
    assert [p["titulo"] for p in cuenta.publicaciones("AURICULARES inalambricos")] == [
        "Auriculares inalámbricos con cancelación de ruido"
    ]
    monitor = cuenta.publicaciones("monitor 27")[0]
    assert monitor["stock_publicado"] == 1 and monitor["precio"] == "$480.000"
    assert len(cuenta.publicaciones()) == 6


def test_pesos_con_separador_de_miles():
    assert pesos(1234567) == "$1.234.567"
    assert pesos(500) == "$500"


def test_las_herramientas_son_de_lectura_y_resumen_lo_obtenido(cuenta):
    herramientas = {h.nombre: h for h in herramientas_mercadolibre(cuenta)}

    assert set(herramientas) == {
        "ml_preguntas_sin_responder", "ml_pedidos", "ml_reclamos_abiertos", "ml_publicaciones",
    }
    assert all(h.origen == "Mercado Libre" for h in herramientas.values())

    preguntas = herramientas["ml_preguntas_sin_responder"].ejecutar()
    assert preguntas.datos["total"] == 4
    assert preguntas.resumen == "4 preguntas sin responder"
    assert herramientas["ml_pedidos"].ejecutar(estado="demorado").resumen == "1 pedido (demorado)"
    assert herramientas["ml_publicaciones"].ejecutar(texto="monitor").resumen == "1 publicación"
