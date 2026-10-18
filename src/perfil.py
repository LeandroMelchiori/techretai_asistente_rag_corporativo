"""
Perfil de empresa: lo que cambia de una empresa a otra.

El resto del código es genérico. Nombre de la empresa y del asistente, textos de
la interfaz, categorías, preguntas sugeridas, conectores y qué puede ver cada
público se leen de ``perfil.toml``, dentro del directorio que indica la variable
de entorno ``PERFIL``. Sumar una empresa es crear su carpeta en ``perfiles/`` con
ese archivo y sus documentos.

Públicos (``Acceso``):
    - "empleado": documentos internos y, si los hay, los conectores (agente).
    - "cliente": sólo las categorías públicas, sin conectores. Existe si el
      perfil tiene la sección [clientes]; si no, el asistente es sólo interno.
"""
from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Literal

from .config import settings

Acceso = Literal["cliente", "empleado"]

ARCHIVO = "perfil.toml"
ICONO_POR_DEFECTO = ":material/chat:"
# Chroma exige nombres de colección ASCII que empiecen con letra o número.
_ID_VALIDO = re.compile(r"[a-z0-9][a-z0-9_-]{1,40}")
# Conectores disponibles y sus modos. "demo" usa los datos ficticios de
# <perfil>/demo/<conector>.json; la conexión a la API real se suma por conector.
CONECTORES = {"mercadolibre": {"demo"}}
_PUBLICOS = {"clientes": "cliente", "empleados": "empleado"}


@dataclass(frozen=True)
class Sugerencia:
    icono: str
    texto: str
    para: Acceso = "empleado"


@dataclass(frozen=True)
class Perfil:
    id: str
    directorio: Path
    empresa: str
    descripcion_empresa: str
    asistente: str
    descripcion_asistente: str
    bienvenida_empleados: str
    resaltado: str = ""
    categorias: Dict[str, str] = field(default_factory=dict)
    sugerencias: List[Sugerencia] = field(default_factory=list)
    # Conector -> modo (por ejemplo {"mercadolibre": "demo"}). Sin conectores, el
    # asistente sólo busca en los documentos.
    conectores: Dict[str, str] = field(default_factory=dict)
    # Público de clientes: lo único que pueden consultar sin iniciar sesión.
    bienvenida_clientes: str = ""
    categorias_publicas: List[str] = field(default_factory=list)

    @property
    def coleccion(self) -> str:
        """Nombre de la colección de la base vectorial de esta empresa."""
        return f"{self.id}_docs"

    @property
    def atiende_clientes(self) -> bool:
        return bool(self.categorias_publicas)

    def categoria(self, clave: str) -> str:
        """Nombre visible de una categoría (la clave es la subcarpeta)."""
        return self.categorias.get(clave, clave)

    def bienvenida(self, acceso: Acceso) -> str:
        return self.bienvenida_clientes if acceso == "cliente" else self.bienvenida_empleados

    def sugerencias_para(self, acceso: Acceso) -> List[Sugerencia]:
        return [s for s in self.sugerencias if s.para == acceso]


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
    categorias = {str(k): str(v) for k, v in datos.get("categorias", {}).items()}

    sugerencias = []
    for i, s in enumerate(datos.get("sugerencias", []), start=1):
        texto = str(s.get("texto", "")).strip()
        if not texto:
            raise PerfilInvalido(f"{origen}: la sugerencia {i} no tiene texto.")
        para = s.get("para", "empleados")
        if para not in _PUBLICOS:
            raise PerfilInvalido(f"{origen}: la sugerencia {i} tiene que tener para = \"clientes\" o \"empleados\".")
        sugerencias.append(Sugerencia(
            icono=str(s.get("icono") or ICONO_POR_DEFECTO), texto=texto, para=_PUBLICOS[para],
        ))

    conectores = {}
    for nombre, modo in datos.get("conectores", {}).items():
        if nombre not in CONECTORES:
            raise PerfilInvalido(f"{origen}: conector desconocido '{nombre}' (disponibles: {', '.join(CONECTORES)}).")
        if modo not in CONECTORES[nombre]:
            modos = ", ".join(sorted(CONECTORES[nombre]))
            raise PerfilInvalido(f"{origen}: el conector '{nombre}' admite los modos: {modos}.")
        conectores[nombre] = modo

    bienvenida_clientes, categorias_publicas = "", []
    if "clientes" in datos:
        bienvenida_clientes = _texto(datos, "clientes", "bienvenida", origen)
        categorias_publicas = [str(c) for c in datos["clientes"].get("categorias", [])]
        if not categorias_publicas:
            raise PerfilInvalido(f"{origen}: [clientes] categorias no puede estar vacía.")
        desconocidas = set(categorias_publicas) - set(categorias)
        if desconocidas:
            raise PerfilInvalido(
                f"{origen}: [clientes] categorías desconocidas: {', '.join(sorted(desconocidas))}."
            )

    return Perfil(
        id=id_,
        directorio=directorio,
        empresa=_texto(datos, "empresa", "nombre", origen),
        descripcion_empresa=_texto(datos, "empresa", "descripcion", origen),
        asistente=_texto(datos, "asistente", "nombre", origen),
        descripcion_asistente=_texto(datos, "asistente", "descripcion", origen),
        bienvenida_empleados=_texto(datos, "empleados", "bienvenida", origen),
        resaltado=_texto(datos, "asistente", "resaltado", origen, obligatorio=False),
        categorias=categorias,
        sugerencias=sugerencias,
        conectores=conectores,
        bienvenida_clientes=bienvenida_clientes,
        categorias_publicas=categorias_publicas,
    )


@lru_cache(maxsize=1)
def perfil_activo() -> Perfil:
    """El perfil configurado en ``PERFIL`` (se lee una sola vez por proceso)."""
    return cargar(settings.perfil_dir)
