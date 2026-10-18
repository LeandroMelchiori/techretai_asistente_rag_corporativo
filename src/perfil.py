"""
Perfil de empresa: lo que cambia de una empresa a otra.

El resto del código es genérico. Nombre de la empresa y del asistente, textos de
la interfaz, categorías y preguntas sugeridas se leen de ``perfil.toml``, dentro
del directorio que indica la variable de entorno ``PERFIL``. Sumar una empresa es
crear su carpeta en ``perfiles/`` con ese archivo y sus documentos.
"""
from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Dict, List

from .config import settings

ARCHIVO = "perfil.toml"
ICONO_POR_DEFECTO = ":material/chat:"
# Chroma exige nombres de colección ASCII que empiecen con letra o número.
_ID_VALIDO = re.compile(r"[a-z0-9][a-z0-9_-]{1,40}")


@dataclass(frozen=True)
class Sugerencia:
    icono: str
    texto: str


@dataclass(frozen=True)
class Perfil:
    id: str
    empresa: str
    descripcion_empresa: str
    asistente: str
    descripcion_asistente: str
    bienvenida: str
    resaltado: str = ""
    categorias: Dict[str, str] = field(default_factory=dict)
    sugerencias: List[Sugerencia] = field(default_factory=list)

    @property
    def coleccion(self) -> str:
        """Nombre de la colección de la base vectorial de esta empresa."""
        return f"{self.id}_docs"

    def categoria(self, clave: str) -> str:
        """Nombre visible de una categoría (la clave es la subcarpeta)."""
        return self.categorias.get(clave, clave)


class PerfilInvalido(RuntimeError):
    pass


def _texto(datos: dict, seccion: str, clave: str, origen: Path, obligatorio: bool = True) -> str:
    nombre = f"[{seccion}] {clave}" if seccion else clave
    tabla = datos.get(seccion, {}) if seccion else datos
    valor = tabla.get(clave, "") if isinstance(tabla, dict) else None
    if not isinstance(valor, str):
        raise PerfilInvalido(f"{origen}: {nombre} tiene que ser texto.")
    valor = valor.strip()
    if obligatorio and not valor:
        raise PerfilInvalido(f"{origen}: falta {nombre}.")
    return valor


def cargar(directorio: Path) -> Perfil:
    """Lee y valida el perfil de ``directorio``."""
    origen = directorio / ARCHIVO
    if not origen.is_file():
        raise PerfilInvalido(
            f"No existe {origen}. Revisá la variable PERFIL (directorio del perfil de la empresa)."
        )
    try:
        datos = tomllib.loads(origen.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise PerfilInvalido(f"{origen}: TOML inválido ({e}).") from e

    id_ = _texto(datos, "", "id", origen)
    if not _ID_VALIDO.fullmatch(id_):
        raise PerfilInvalido(
            f"{origen}: 'id' admite minúsculas sin acentos, números, '-' y '_' (2 a 41 caracteres)."
        )

    sugerencias = []
    for i, s in enumerate(datos.get("sugerencias", []), start=1):
        texto = str(s.get("texto", "")).strip()
        if not texto:
            raise PerfilInvalido(f"{origen}: la sugerencia {i} no tiene texto.")
        sugerencias.append(Sugerencia(icono=str(s.get("icono") or ICONO_POR_DEFECTO), texto=texto))

    return Perfil(
        id=id_,
        empresa=_texto(datos, "empresa", "nombre", origen),
        descripcion_empresa=_texto(datos, "empresa", "descripcion", origen),
        asistente=_texto(datos, "asistente", "nombre", origen),
        descripcion_asistente=_texto(datos, "asistente", "descripcion", origen),
        bienvenida=_texto(datos, "asistente", "bienvenida", origen),
        resaltado=_texto(datos, "asistente", "resaltado", origen, obligatorio=False),
        categorias={str(k): str(v) for k, v in datos.get("categorias", {}).items()},
        sugerencias=sugerencias,
    )


@lru_cache(maxsize=1)
def perfil_activo() -> Perfil:
    """El perfil configurado en ``PERFIL`` (se lee una sola vez por proceso)."""
    return cargar(settings.perfil_dir)
