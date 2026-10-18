"""Tests de las respuestas guardadas para las preguntas sugeridas."""
from src.cache import CacheDeRespuestas


class Reloj:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def test_devuelve_lo_guardado_hasta_que_vence():
    reloj = Reloj()
    cache = CacheDeRespuestas(duracion_s=60, reloj=reloj)
    clave = ("techretail", "cliente", "¿Cuánto cuesta el envío?")

    assert cache.obtener(clave) is None
    cache.guardar(clave, {"texto": "$11.900"})
    reloj.t = 59
    assert cache.obtener(clave) == {"texto": "$11.900"}
    reloj.t = 61
    assert cache.obtener(clave) is None


def test_cada_publico_tiene_sus_respuestas():
    cache = CacheDeRespuestas(duracion_s=60, reloj=Reloj())
    cache.guardar(("techretail", "empleado", "¿Hay pedidos demorados?"), {"texto": "Sí"})

    assert cache.obtener(("techretail", "cliente", "¿Hay pedidos demorados?")) is None


def test_con_duracion_cero_no_guarda():
    cache = CacheDeRespuestas(duracion_s=0, reloj=Reloj())
    cache.guardar("x", {"texto": "a"})

    assert cache.obtener("x") is None
