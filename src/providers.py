"""
Capa de proveedores: aísla al resto del código de qué LLM / modelo de
embeddings se usa. Cambiar de Gemini a OpenAI (o a futuro OCI Generative AI)
es solo cambiar ``LLM_PROVIDER`` en el .env.

Expone dos funciones de alto nivel:
    - embed_texts(textos, is_query=False) -> lista de vectores
    - generate(system_prompt, user_prompt) -> texto de respuesta
"""
from __future__ import annotations

from functools import lru_cache
from typing import List

from .config import settings


# --------------------------------------------------------------------------
#  Gemini
# --------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _gemini():
    import google.generativeai as genai

    genai.configure(api_key=settings.google_api_key)
    return genai


def _gemini_embed(texts: List[str], is_query: bool) -> List[List[float]]:
    genai = _gemini()
    task = "retrieval_query" if is_query else "retrieval_document"
    vectors: List[List[float]] = []
    # La API de Gemini embebe de a un texto por llamada de forma estable.
    for text in texts:
        resp = genai.embed_content(
            model=f"models/{settings.gemini_embed_model}",
            content=text,
            task_type=task,
        )
        vectors.append(resp["embedding"])
    return vectors


def _gemini_generate(system_prompt: str, user_prompt: str) -> str:
    genai = _gemini()
    model = genai.GenerativeModel(
        model_name=settings.gemini_chat_model,
        system_instruction=system_prompt,
    )
    resp = model.generate_content(
        user_prompt,
        generation_config={"temperature": 0.2},
    )
    return (resp.text or "").strip()


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
