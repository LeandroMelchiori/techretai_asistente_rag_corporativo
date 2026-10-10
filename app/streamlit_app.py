"""
Interfaz de chat del agente TechRetAI.

Chat web estilo asistente de IA: varias conversaciones con historial en la barra
lateral (crear, renombrar, eliminar), marca propia, preguntas de ejemplo,
fuentes citadas y feedback.

Nota: las conversaciones viven en la sesión del navegador (se pierden al recargar
o reiniciar el servidor).

Ejecutar con:  streamlit run app/streamlit_app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import vectorstore  # noqa: E402
from src.agent import responder  # noqa: E402
from src.config import settings  # noqa: E402
from src.logging_utils import registrar  # noqa: E402

ACCENT = "#12B5A5"

st.set_page_config(page_title="TechRetAI", page_icon="🤖", layout="centered")

EJEMPLOS = [
    "¿Cuántos días de vacaciones me corresponden con 6 años de antigüedad?",
    "¿Qué comisión cobra MercadoPago por tarjeta de crédito?",
    "¿Cuánto cuesta el plan Growth y qué incluye?",
    "¿Cómo funciona la facturación automática contra ARCA?",
]


# --------------------------------------------------------------------------
#  Estilos
# --------------------------------------------------------------------------
st.markdown(
    f"""
    <style>
    .marca {{ font-size: 2.5rem; font-weight: 800; line-height: 1.1; margin-bottom: .2rem; }}
    .marca .ai {{ color: {ACCENT}; }}
    .subt {{ color: #B4BAC2; font-size: 1.02rem; margin-bottom: .3rem; }}
    /* Objetivo táctil mínimo 44px (accesibilidad / interacción) */
    div[data-testid="stButton"] > button {{ min-height: 44px; }}
    /* Botones "secundarios" con aspecto de chip/lista */
    div[data-testid="stButton"] > button:not([kind="primary"]):not([data-testid="stBaseButton-primary"]) {{
        text-align: left; border: 1px solid #2A2F3A; background: #161A23;
        border-radius: 10px; padding: .5rem .7rem; font-weight: 500;
        white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
        transition: border-color .15s ease;
    }}
    div[data-testid="stButton"] > button:not([kind="primary"]):hover {{ border-color: {ACCENT}; color: {ACCENT}; }}
    /* Botón "primario" = conversación activa (texto oscuro sobre el acento, mejor contraste) */
    div[data-testid="stButton"] > button[kind="primary"],
    div[data-testid="stButton"] > button[data-testid="stBaseButton-primary"] {{
        text-align: left; border-radius: 10px; padding: .5rem .7rem; font-weight: 700;
        color: #052A26;
        white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    }}
    /* Respeta la preferencia de movimiento reducido */
    @media (prefers-reduced-motion: reduce) {{
        * {{ transition: none !important; animation: none !important; }}
    }}
    </style>
    """,
    unsafe_allow_html=True,
)


# --------------------------------------------------------------------------
#  Estado: varias conversaciones
# --------------------------------------------------------------------------
def _crear_conversacion() -> int:
    cid = st.session_state.contador
    st.session_state.contador += 1
    st.session_state.conversaciones[cid] = {"titulo": "Nueva conversación", "mensajes": []}
    st.session_state.conv_actual = cid
    return cid


def ir_a_nueva() -> None:
    """Va a una conversación vacía (reutiliza si ya hay una, para no duplicar)."""
    for cid, c in st.session_state.conversaciones.items():
        if not c["mensajes"]:
            st.session_state.conv_actual = cid
            return
    _crear_conversacion()


if "conversaciones" not in st.session_state:
    st.session_state.conversaciones = {}
    st.session_state.contador = 0
    st.session_state.renombrando = None
    _crear_conversacion()


def conv_actual() -> dict:
    return st.session_state.conversaciones[st.session_state.conv_actual]


def eliminar(cid: int) -> None:
    st.session_state.conversaciones.pop(cid, None)
    if st.session_state.get("renombrando") == cid:
        st.session_state.renombrando = None
    if st.session_state.conv_actual == cid:
        ir_a_nueva()


# --------------------------------------------------------------------------
#  Procesamiento de una pregunta (sobre la conversación activa)
# --------------------------------------------------------------------------
def procesar(pregunta: str) -> None:
    """Registra la pregunta del usuario y deja la respuesta pendiente.

    La respuesta se genera en el siguiente render mostrando un indicador de
    carga, para no congelar la interfaz durante la llamada al LLM.
    """
    conv = conv_actual()
    conv["mensajes"].append({"rol": "user", "texto": pregunta})
    if conv["titulo"] == "Nueva conversación":
        conv["titulo"] = pregunta[:38] + ("…" if len(pregunta) > 38 else "")
    st.rerun()


def responder_pendiente(conv: dict) -> None:
    """Si la última intervención es del usuario, genera la respuesta con feedback de carga."""
    with st.chat_message("assistant", avatar="🤖"):
        with st.spinner("Buscando en los documentos…"):
            try:
                settings.validate()
                resp = responder(conv["mensajes"][-1]["texto"])
                registrar(resp)
                conv["mensajes"].append(
                    {
                        "rol": "assistant",
                        "texto": resp.texto,
                        "fuentes": resp.fuentes,
                        "respuesta_obj": resp,
                        "feedback_dado": False,
                    }
                )
            except Exception as e:  # noqa: BLE001
                conv["mensajes"].append(
                    {"rol": "assistant", "texto": f"⚠️ Ocurrió un error: {e}", "fuentes": []}
                )
    st.rerun()


# --------------------------------------------------------------------------
#  Barra lateral: marca + lista de conversaciones + estado
# --------------------------------------------------------------------------
with st.sidebar:
    st.markdown(f"### 🤖 TechRet<span style='color:{ACCENT}'>AI</span>", unsafe_allow_html=True)
    st.caption("Asistente corporativo de TechRetail Solutions")

    if st.button("➕  Nueva conversación", use_container_width=True):
        ir_a_nueva()
        st.rerun()

    st.markdown("**Conversaciones**")

    # Solo se listan las conversaciones que ya tienen contenido (más recientes primero).
    listadas = [
        cid for cid in reversed(list(st.session_state.conversaciones.keys()))
        if st.session_state.conversaciones[cid]["mensajes"]
    ]

    if not listadas:
        st.caption("_Sin conversaciones aún. Escribí abajo para empezar._")

    for cid in listadas:
        conv = st.session_state.conversaciones[cid]
        activa = cid == st.session_state.conv_actual

        if st.session_state.renombrando == cid:
            # Modo edición del nombre.
            nuevo = st.text_input(
                "Nuevo nombre", value=conv["titulo"], key=f"rn_{cid}",
                label_visibility="collapsed",
            )
            c1, c2 = st.columns(2)
            if c1.button("Guardar", key=f"save_{cid}", use_container_width=True):
                conv["titulo"] = nuevo.strip() or conv["titulo"]
                st.session_state.renombrando = None
                st.rerun()
            if c2.button("Cancelar", key=f"cancel_{cid}", use_container_width=True):
                st.session_state.renombrando = None
                st.rerun()
        else:
            # Fila normal: seleccionar | renombrar | eliminar.
            sel, ren, dele = st.columns([0.7, 0.15, 0.15])
            if sel.button(
                conv["titulo"], key=f"conv_{cid}", use_container_width=True,
                type="primary" if activa else "secondary", help=conv["titulo"],
            ):
                st.session_state.conv_actual = cid
                st.rerun()
            if ren.button("✏️", key=f"ed_{cid}", help="Renombrar"):
                st.session_state.renombrando = cid
                st.rerun()
            if dele.button("🗑️", key=f"del_{cid}", help="Eliminar"):
                eliminar(cid)
                st.rerun()

    st.divider()
    st.markdown("**Estado**")
    st.caption(f"Modelo: `{settings.provider}`")
    try:
        st.caption(f"Documentos indexados: **{vectorstore.stats()['fragmentos']}** fragmentos")
    except Exception:
        st.caption("Base de conocimiento: (no inicializada)")

    st.divider()
    st.caption(
        "⚠️ Estás conversando con un **agente de IA**. Las respuestas se basan en "
        "documentos internos y pueden contener errores: verificá en la fuente citada."
    )


# --------------------------------------------------------------------------
#  Encabezado + conversación activa
# --------------------------------------------------------------------------
st.markdown(
    "<div class='marca'>TechRet<span class='ai'>AI</span></div>"
    "<div class='subt'>Preguntá lo que necesites sobre la documentación interna de la empresa.</div>",
    unsafe_allow_html=True,
)
st.write("")

conv = conv_actual()

if not conv["mensajes"]:
    st.markdown("##### 💡 Probá con una de estas preguntas")
    cols = st.columns(2)
    for i, ejemplo in enumerate(EJEMPLOS):
        if cols[i % 2].button(ejemplo, key=f"ej_{i}", use_container_width=True):
            procesar(ejemplo)

for i, msg in enumerate(conv["mensajes"]):
    avatar = "🤖" if msg["rol"] == "assistant" else "🧑"
    with st.chat_message(msg["rol"], avatar=avatar):
        st.markdown(msg["texto"])
        if msg.get("fuentes"):
            with st.expander("📄 Fuentes citadas"):
                for f in msg["fuentes"]:
                    st.markdown(
                        f"- **{f['archivo']}** · _{f['categoria']}_ "
                        f"({f['formato']}) — relevancia {f['relevancia']:.2f}"
                    )
        if msg["rol"] == "assistant" and msg.get("respuesta_obj") and not msg.get("feedback_dado"):
            c1, c2, _ = st.columns([1, 1, 8])
            cid = st.session_state.conv_actual
            if c1.button("👍", key=f"up_{cid}_{i}"):
                registrar(msg["respuesta_obj"], feedback="positivo")
                conv["mensajes"][i]["feedback_dado"] = True
                st.toast("¡Gracias por tu feedback!")
                st.rerun()
            if c2.button("👎", key=f"down_{cid}_{i}"):
                registrar(msg["respuesta_obj"], feedback="negativo")
                conv["mensajes"][i]["feedback_dado"] = True
                st.toast("Feedback registrado, lo tendremos en cuenta.")
                st.rerun()


# Si la última intervención es del usuario, la respuesta está pendiente de generarse.
if conv["mensajes"] and conv["mensajes"][-1]["rol"] == "user":
    responder_pendiente(conv)


pregunta = st.chat_input("Escribí tu pregunta...")
if pregunta:
    procesar(pregunta)
