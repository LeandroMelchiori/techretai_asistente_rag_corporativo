"""
Tests de los límites de uso: tope por cliente (ventana deslizante) y tope diario.

Se usa un reloj simulado para no depender del tiempo real.
"""
from src.limites import DIA_S, LimitadorDeConsultas


class Reloj:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def test_tope_por_cliente_y_espera():
    reloj = Reloj()
    lim = LimitadorDeConsultas(por_cliente=2, ventana_s=60, por_dia=0, reloj=reloj)

    assert lim.permitir("a").permitido
    reloj.t += 10
    assert lim.permitir("a").permitido

    reloj.t += 5
    bloqueo = lim.permitir("a")
    assert not bloqueo.permitido
    assert bloqueo.motivo == "cliente"
    assert bloqueo.espera_s == 45  # la primera consulta sale de la ventana en 45 s

    # Otro cliente no se ve afectado.
    assert lim.permitir("b").permitido

    # Cuando la primera consulta sale de la ventana, vuelve a permitir.
    reloj.t += 45
    assert lim.permitir("a").permitido


def test_tope_diario_global():
    reloj = Reloj()
    lim = LimitadorDeConsultas(por_cliente=0, ventana_s=60, por_dia=3, reloj=reloj)

    for cliente in ("a", "b", "c"):
        assert lim.permitir(cliente).permitido
    bloqueo = lim.permitir("d")
    assert not bloqueo.permitido
    assert bloqueo.motivo == "global"

    reloj.t += DIA_S
    assert lim.permitir("d").permitido


def test_consulta_rechazada_no_consume_cupo():
    reloj = Reloj()
    lim = LimitadorDeConsultas(por_cliente=1, ventana_s=60, por_dia=2, reloj=reloj)

    assert lim.permitir("a").permitido
    for _ in range(5):
        assert not lim.permitir("a").permitido  # rechazos: no suman al tope diario
    assert lim.permitir("b").permitido


def test_cero_desactiva_los_topes():
    lim = LimitadorDeConsultas(por_cliente=0, ventana_s=60, por_dia=0)
    assert all(lim.permitir("a").permitido for _ in range(100))


def test_las_llamadas_extra_del_agente_cuentan_para_el_tope_global():
    reloj = Reloj()
    lim = LimitadorDeConsultas(por_cliente=0, ventana_s=60, por_dia=5, reloj=reloj)

    assert lim.permitir("a").permitido  # 1 llamada
    lim.consumir(3)  # el agente hizo 4 en total
    assert lim.permitir("b").permitido  # 5
    decision = lim.permitir("c")

    assert not decision.permitido and decision.motivo == "global"
    reloj.t += 24 * 60 * 60
    assert lim.permitir("c").permitido
