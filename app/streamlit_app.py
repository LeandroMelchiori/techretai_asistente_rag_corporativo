"""
Interfaz de chat del agente (etapa 6 del desafío).

Chat web simple pero funcional con:
- Aviso claro de que se conversa con un agente de IA.
- Historial de conversación dentro de la sesión.
- Visualización de las fuentes/documentos citados en cada respuesta.
- Botones de feedback (👍 / 👎) que quedan registrados en el log.
- Filtro opcional por categoría de documento.

Ejecutar con:  streamlit run app/streamlit_app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

# Permite importar el paquete src cuando Streamlit ejecuta este archivo.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import vectorstore  # noqa: E402
from src.agent import responder  # noqa: E402
from src.config import settings  # noqa: E402
from src.logging_utils import registrar  # noqa: E402

st.set_page_config(page_title="Asistente TechRetail", page_icon="🤖", layout="centered")

CATEGORIAS = [
    "Todas",
    "rrhh",
    "financiero",
    "legal",
    "operacional",
    "comercial",
    "estrategico",
    "datos_sistemas",
]


# --------------------------------------------------------------------------
#  Barra lateral
# --------------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ Configuración")
    st.caption(f"Proveedor LLM: **{settings.provider}**")
    try:
        st.caption(f"Fragmentos indexados: **{vectorstore.stats()['fragmentos']}**")
    except Exception:
        st.caption("Fragmentos indexados: (base no inicializada)")

    categoria = st.selectbox("Filtrar por área", CATEGORIAS, index=0)
    categoria = None if categoria == "Todas" else categoria

    if st.button("🧹 Limpiar conversación"):
        st.session_state.mensajes = []
        st.rerun()

    st.divider()
    st.caption(
        "⚠️ Estás conversando con un **agente de IA**. Las respuestas se basan "
        "en documentos internos de TechRetail y pueden contener errores. "
        "Verificá en la fuente citada."
    )


# --------------------------------------------------------------------------
#  Estado de la conversación
# --------------------------------------------------------------------------
st.title("🤖 Asistente Corporativo TechRetail")
st.caption("Respondo preguntas sobre los documentos internos de la empresa.")

if "mensajes" not in st.session_state:
    st.session_state.mensajes = []

# Vuelve a dibujar el historial.
for i, msg in enumerate(st.session_state.mensajes):
    with st.chat_message(msg["rol"]):
        st.markdown(msg["texto"])
        if msg.get("fuentes"):
            with st.expander("📄 Fuentes citadas"):
                for f in msg["fuentes"]:
                    st.markdown(
                        f"- **{f['archivo']}** · _{f['categoria']}_ "
                        f"({f['formato']}) — relevancia {f['relevancia']:.2f}"
                    )
        # Botones de feedback solo en las respuestas del asistente.
        if msg["rol"] == "assistant" and not msg.get("feedback_dado"):
            col1, col2, _ = st.columns([1, 1, 6])
            if col1.button("👍", key=f"up_{i}"):
                registrar(msg["respuesta_obj"], feedback="positivo")
                st.session_state.mensajes[i]["feedback_dado"] = True
                st.toast("¡Gracias por tu feedback!")
                st.rerun()
            if col2.button("👎", key=f"down_{i}"):
                registrar(msg["respuesta_obj"], feedback="negativo")
                st.session_state.mensajes[i]["feedback_dado"] = True
                st.toast("Feedback registrado, lo tendremos en cuenta.")
                st.rerun()


# --------------------------------------------------------------------------
#  Entrada del usuario
# --------------------------------------------------------------------------
pregunta = st.chat_input("Escribí tu pregunta...")
if pregunta:
    st.session_state.mensajes.append({"rol": "user", "texto": pregunta})
    with st.chat_message("user"):
        st.markdown(pregunta)

    with st.chat_message("assistant"):
        with st.spinner("Buscando en los documentos..."):
            try:
                settings.validate()
                resp = responder(pregunta, categoria=categoria)
                registrar(resp)  # registro de ejecución (sin feedback aún)
            except Exception as e:  # noqa: BLE001
                st.error(f"Ocurrió un error: {e}")
                st.stop()
        st.markdown(resp.texto)

    st.session_state.mensajes.append(
        {
            "rol": "assistant",
            "texto": resp.texto,
            "fuentes": resp.fuentes,
            "respuesta_obj": resp,
            "feedback_dado": False,
        }
    )
    st.rerun()
