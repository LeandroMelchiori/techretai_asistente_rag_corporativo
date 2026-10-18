"""
Capa de proveedores: aísla al resto del código de qué LLM / modelo de
embeddings se usa. Cambiar de Gemini a OpenAI (o a futuro OCI Generative AI)
es solo cambiar ``LLM_PROVIDER`` en el .env.

Expone cuatro funciones de alto nivel:
    - embed_texts(textos, is_query=False) -> lista de vectores
    - generate(system_prompt, user_prompt) -> texto de respuesta
    - generate_stream(system_prompt, user_prompt) -> partes del texto a medida
      que el modelo las genera (para mostrarlas en vivo en la interfaz)
    - generate_con_herramientas(...) -> como generate_stream, pero el modelo
      puede pedir herramientas antes de responder (sólo Gemini por ahora)
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any, Callable, Dict, Iterator, List

from .config import settings
from .herramientas.base import Herramienta


# --------------------------------------------------------------------------
#  Gemini (librería google-genai)
# --------------------------------------------------------------------------
# Textos por llamada al generar embeddings de documentos.
_LOTE_EMBEDDINGS = 50


@lru_cache(maxsize=1)
def _gemini():
    from google import genai

    return genai.Client(api_key=settings.google_api_key)


def _gemini_config(system_prompt: str, **extra):
    from google.genai import types

    return types.GenerateContentConfig(system_instruction=system_prompt, temperature=0.2, **extra)


def _gemini_embed(texts: List[str], is_query: bool) -> List[List[float]]:
    from google.genai import types

    config = types.EmbedContentConfig(task_type="RETRIEVAL_QUERY" if is_query else "RETRIEVAL_DOCUMENT")
    vectors: List[List[float]] = []
    for i in range(0, len(texts), _LOTE_EMBEDDINGS):
        resp = _gemini().models.embed_content(
            model=settings.gemini_embed_model,
            contents=texts[i : i + _LOTE_EMBEDDINGS],
            config=config,
        )
        vectors.extend(list(e.values) for e in resp.embeddings)
    return vectors


def _gemini_generate(system_prompt: str, user_prompt: str) -> str:
    resp = _gemini().models.generate_content(
        model=settings.gemini_chat_model,
        contents=user_prompt,
        config=_gemini_config(system_prompt),
    )
    return (resp.text or "").strip()


def _gemini_generate_stream(system_prompt: str, user_prompt: str) -> Iterator[str]:
    for parte in _gemini().models.generate_content_stream(
        model=settings.gemini_chat_model,
        contents=user_prompt,
        config=_gemini_config(system_prompt),
    ):
        # Partes sin texto (p. ej. sólo metadatos de cierre): se ignoran.
        if parte.text:
            yield parte.text


def _partes(respuesta) -> list:
    if not respuesta.candidates or not respuesta.candidates[0].content:
        return []
    return respuesta.candidates[0].content.parts or []


def _gemini_generate_con_herramientas(
    system_prompt: str,
    user_prompt: str,
    herramientas: List[Herramienta],
    ejecutar: Callable[[str, Dict[str, Any]], Dict[str, Any]],
    max_rondas: int,
) -> Iterator[str]:
    from google.genai import types

    declaraciones = [
        types.FunctionDeclaration(name=h.nombre, description=h.descripcion, parameters_json_schema=h.parametros)
        for h in herramientas
    ]
    con_herramientas = _gemini_config(
        system_prompt,
        tools=[types.Tool(function_declarations=declaraciones)],
        # Las llamadas las ejecuta el agente, no la librería: así se controlan y registran.
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )
    # En la última ronda el modelo ya no puede pedir herramientas: tiene que responder.
    sin_herramientas = con_herramientas.model_copy(
        update={"tool_config": types.ToolConfig(
            function_calling_config=types.FunctionCallingConfig(mode="NONE")
        )}
    )
    historial = [types.Content(role="user", parts=[types.Part.from_text(text=user_prompt)])]

    for ronda in range(max_rondas + 1):
        config = con_herramientas if ronda < max_rondas else sin_herramientas
        llamadas = []
        for respuesta in _gemini().models.generate_content_stream(
            model=settings.gemini_chat_model, contents=historial, config=config
        ):
            for parte in _partes(respuesta):
                if parte.function_call:
                    llamadas.append(parte)
                elif parte.text and not parte.thought:
                    yield parte.text
        if not llamadas:
            return
        # Se devuelven las partes tal cual (con su firma de razonamiento, que
        # los modelos Gemini 3 exigen para continuar la conversación).
        historial.append(types.Content(role="model", parts=llamadas))
        historial.append(types.Content(role="user", parts=[
            types.Part.from_function_response(
                name=p.function_call.name,
                response=ejecutar(p.function_call.name, dict(p.function_call.args or {})),
            )
            for p in llamadas
        ]))


# --------------------------------------------------------------------------
#  OpenAI
# --------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _openai():
    from openai import OpenAI

    return OpenAI(api_key=settings.openai_api_key)


def _openai_embed(texts: List[str], is_query: bool) -> List[List[float]]:
    client = _openai()
    resp = client.embeddings.create(model=settings.openai_embed_model, input=texts)
    return [item.embedding for item in resp.data]


def _openai_generate(system_prompt: str, user_prompt: str) -> str:
    client = _openai()
    resp = client.chat.completions.create(
        model=settings.openai_chat_model,
        temperature=0.2,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return (resp.choices[0].message.content or "").strip()


def _openai_generate_stream(system_prompt: str, user_prompt: str) -> Iterator[str]:
    client = _openai()
    resp = client.chat.completions.create(
        model=settings.openai_chat_model,
        temperature=0.2,
        stream=True,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    for parte in resp:
        if parte.choices and parte.choices[0].delta.content:
            yield parte.choices[0].delta.content


# --------------------------------------------------------------------------
#  Interfaz pública
# --------------------------------------------------------------------------
def embed_texts(texts: List[str], is_query: bool = False) -> List[List[float]]:
    """Devuelve un vector de embedding por cada texto de entrada.

    ``is_query=True`` marca que el texto es una pregunta (algunos modelos
    optimizan el embedding según sea documento o consulta).
    """
    if not texts:
        return []
    if settings.provider == "gemini":
        return _gemini_embed(texts, is_query)
    return _openai_embed(texts, is_query)


def generate(system_prompt: str, user_prompt: str) -> str:
    """Genera la respuesta del LLM a partir del prompt de sistema y el usuario."""
    if settings.provider == "gemini":
        return _gemini_generate(system_prompt, user_prompt)
    return _openai_generate(system_prompt, user_prompt)


def generate_stream(system_prompt: str, user_prompt: str) -> Iterator[str]:
    """Como ``generate``, pero entrega el texto en partes a medida que se genera."""
    if settings.provider == "gemini":
        return _gemini_generate_stream(system_prompt, user_prompt)
    return _openai_generate_stream(system_prompt, user_prompt)


def generate_con_herramientas(
    system_prompt: str,
    user_prompt: str,
    herramientas: List[Herramienta],
    ejecutar: Callable[[str, Dict[str, Any]], Dict[str, Any]],
    max_rondas: int = 3,
) -> Iterator[str]:
    """Entrega la respuesta en partes; antes, el modelo puede pedir herramientas.

    ``ejecutar(nombre, argumentos)`` corre la herramienta y devuelve el resultado
    que recibe el modelo. Hay como máximo ``max_rondas`` rondas de llamadas;
    después el modelo tiene que responder con lo que obtuvo.
    """
    if settings.provider != "gemini":
        raise RuntimeError("Las herramientas por ahora sólo están disponibles con Gemini.")
    return _gemini_generate_con_herramientas(system_prompt, user_prompt, herramientas, ejecutar, max_rondas)
