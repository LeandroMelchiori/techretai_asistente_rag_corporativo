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

import html
import math
import sys
import uuid
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import vectorstore  # noqa: E402
from src.agent import responder_en_vivo  # noqa: E402
from src.config import settings  # noqa: E402
from src.limites import Decision, LimitadorDeConsultas  # noqa: E402
from src.logging_utils import registrar  # noqa: E402

TITULO_NUEVA = "Nueva conversación"
AVATAR = {"assistant": ":material/smart_toy:", "user": ":material/person:"}

st.set_page_config(page_title="TechRetAI", page_icon=":material/smart_toy:", layout="centered")

CATEGORIAS = {
    "rrhh": "RR. HH.",
    "financiero": "Financiero",
    "legal": "Legal",
    "operacional": "Operaciones",
    "comercial": "Comercial",
    "estrategico": "Estratégico",
    "datos_sistemas": "Datos y sistemas",
}


def nivel_relevancia(valor: float) -> tuple[str, str]:
    """Traduce la similitud coseno a un nivel legible.

    Con gemini-embedding-2 la similitud entre textos sin relación ya ronda 0,5,
    así que un porcentaje crudo confunde. Cortes calibrados con eval/.
    """
    if valor >= 0.70:
        return "alta", "Relevancia alta"
    if valor >= 0.60:
        return "media", "Relevancia media"
    return "baja", "Relevancia baja"


EJEMPLOS = [
    (":material/beach_access:", "¿Cuántos días de vacaciones me corresponden con 6 años de antigüedad?"),
    (":material/credit_card:", "¿Qué comisión cobra MercadoPago por tarjeta de crédito?"),
    (":material/sell:", "¿Cuánto cuesta el plan Growth y qué incluye?"),
    (":material/receipt_long:", "¿Cómo funciona la facturación automática contra ARCA?"),
]


# --------------------------------------------------------------------------
#  Estilos
# --------------------------------------------------------------------------
# Los widgets con key reciben la clase .st-key-<key>, lo que permite dar estilo
# a cada grupo de botones sin afectar al resto de la interfaz.
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Lexend:wght@600;700;800&display=swap');

    :root {
        --accent: #12B5A5;
        --on-accent: #052A26;
        --surface: #161A23;
        --surface-hover: #1B2130;
        --border: #2A2F3A;
        --muted: #B4BAC2;
        --danger: #F87171;
        --radius: 12px;
    }

    /* Marca y títulos */
    .marca, .marca-lateral, .seccion { font-family: 'Lexend', 'Source Sans Pro', sans-serif; }
    .marca { font-size: 2.4rem; font-weight: 800; line-height: 1.1; margin-bottom: .25rem; letter-spacing: -.01em; }
    .marca-lateral { font-size: 1.35rem; font-weight: 700; margin-bottom: .1rem; }
    .marca .ai, .marca-lateral .ai { color: var(--accent); }
    .subt { color: var(--muted); font-size: 1.02rem; line-height: 1.5; }
    .seccion { font-size: 1rem; font-weight: 600; margin: 1.1rem 0 .5rem; }

    /* Franja decorativa superior e indicador "Running/Stop" de Streamlit: fuera.
       El progreso ya se informa dentro del chat ("Buscando en los documentos…"). */
    [data-testid="stDecoration"], [data-testid="stStatusWidget"] { display: none; }

    /* Fuentes citadas: nivel de relevancia como etiqueta */
    .fuente { display: flex; flex-wrap: wrap; align-items: center; gap: .35rem .6rem; padding: .3rem 0; }
    .fuente .archivo { font-weight: 600; overflow-wrap: anywhere; }
    .fuente .meta { color: var(--muted); font-size: .9rem; }
    .fuente .nivel {
        font-size: .78rem; font-weight: 600; line-height: 1; padding: .3rem .55rem;
        border-radius: 999px; border: 1px solid var(--border); white-space: nowrap;
    }
    .fuente .nivel.alta { color: var(--accent); border-color: var(--accent); }

    /* Base de todos los botones: objetivo táctil de 44px y foco visible.
       Selector descendiente: con "help", Streamlit envuelve el botón en un tooltip. */
    div[data-testid="stButton"] button { min-height: 44px; border-radius: var(--radius); }
    div[data-testid="stButton"] button:focus-visible,
    div[class*="st-key-fb_"] button:focus-visible {
        outline: 2px solid var(--accent); outline-offset: 2px; box-shadow: none;
    }

    /* Feedback (pulgares): el widget nativo usa botones de 24px */
    div[class*="st-key-fb_"] button { min-width: 44px; min-height: 44px; justify-content: center; }

    /* Preguntas sugeridas: tarjetas con el texto completo (salto de línea).
       La altura mínima admite tres líneas para que las tarjetas de una fila coincidan. */
    div[class*="st-key-ej_"] button {
        justify-content: flex-start; align-items: center; text-align: left; gap: .6rem;
        min-height: 5.9rem; padding: .8rem .9rem;
        background: var(--surface); border: 1px solid var(--border);
        transition: border-color .2s ease, background-color .2s ease;
    }
    div[class*="st-key-ej_"] button p {
        white-space: normal; overflow-wrap: anywhere; line-height: 1.4; font-weight: 500;
    }
    div[class*="st-key-ej_"] button span { color: var(--accent); flex-shrink: 0; }
    div[class*="st-key-ej_"] button:hover { border-color: var(--accent); background: var(--surface-hover); }

    /* Conversaciones de la barra lateral: una línea con elipsis */
    div[class*="st-key-conv_"] button { justify-content: flex-start; text-align: left; padding: .5rem .75rem; }
    div[class*="st-key-conv_"] button > div { min-width: 0; max-width: 100%; }
    div[class*="st-key-conv_"] button p {
        white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-weight: 500;
    }
    div[class*="st-key-conv_"] button[kind="primary"] p { color: var(--on-accent); font-weight: 700; }

    /* Botones sólo con ícono: el texto queda disponible para lectores de pantalla */
    div[class*="st-key-ed_"] button, div[class*="st-key-del_"] button {
        position: relative; padding: 0 .6rem; justify-content: center; min-width: 44px;
    }
    /* Sin texto visible al lado, el margen derecho del ícono lo descentraría */
    div[class*="st-key-ed_"] button span, div[class*="st-key-del_"] button span { margin: 0; }
    div[class*="st-key-ed_"] button p, div[class*="st-key-del_"] button p {
        position: absolute; width: 1px; height: 1px; overflow: hidden;
        clip: rect(0 0 0 0); white-space: nowrap;
    }
    div[class*="st-key-del_"] button:hover { border-color: var(--danger); color: var(--danger); }

    /* Pantallas angostas: las tarjetas van en una columna y no necesitan igualar alturas */
    @media (max-width: 640px) {
        div[class*="st-key-ej_"] button { min-height: 0; }
        [data-testid="stMainBlockContainer"] { padding-top: 3.5rem; }
        .marca { font-size: 2rem; }
    }

    /* Respeta la preferencia de movimiento reducido */
    @media (prefers-reduced-motion: reduce) {
        * { transition: none !important; animation: none !important; }
    }
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
    st.session_state.conversaciones[cid] = {"titulo": TITULO_NUEVA, "mensajes": []}
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
#  Límites de uso (protegen la cuota de la API key)
# --------------------------------------------------------------------------
@st.cache_resource
def limitador() -> LimitadorDeConsultas:
    """Un único limitador compartido por todas las sesiones del proceso."""
    return LimitadorDeConsultas(
        por_cliente=settings.rate_limit_per_client,
        ventana_s=settings.rate_limit_window_min * 60,
        por_dia=settings.rate_limit_daily,
    )


def cliente_id() -> str:
    """Identifica al cliente por su IP (la informa Traefik) o, si no, por sesión."""
    ip = st.context.headers.get("X-Real-Ip", "").strip()
    if ip:
        return ip
    return st.session_state.setdefault("sesion_id", uuid.uuid4().hex)


def aviso_limite(decision: Decision) -> str:
    if decision.motivo == "global":
        return "El asistente alcanzó el límite diario de consultas. Volvé a intentarlo más tarde."
    if decision.espera_s < 60:
        espera = f"{decision.espera_s} segundos"
    else:
        minutos = math.ceil(decision.espera_s / 60)
        espera = f"{minutos} minuto{'s' if minutos != 1 else ''}"
    return f"Hiciste varias preguntas seguidas. Podés volver a preguntar en {espera}."


# --------------------------------------------------------------------------
#  Procesamiento de una pregunta (sobre la conversación activa)
# --------------------------------------------------------------------------
def procesar(pregunta: str) -> None:
    """Registra la pregunta del usuario y deja la respuesta pendiente.

    La respuesta se genera en el siguiente render mostrando un indicador de
    carga, para no congelar la interfaz durante la llamada al LLM.
    """
    conv = conv_actual()
    # El campo ya limita el largo; se repite acá por si llega un mensaje armado a mano.
    pregunta = pregunta[: settings.max_question_chars] if settings.max_question_chars else pregunta
    conv["mensajes"].append({"rol": "user", "texto": pregunta})
    if conv["titulo"] == TITULO_NUEVA:
        # El título completo se recorta visualmente en la barra lateral (CSS).
        conv["titulo"] = pregunta[:120]
    st.rerun()


def responder_pendiente(conv: dict) -> None:
    """Genera la respuesta a la última pregunta y la muestra a medida que se escribe."""
    decision = limitador().permitir(cliente_id())
    if not decision.permitido:
        conv["mensajes"].append({"rol": "assistant", "texto": aviso_limite(decision), "aviso": True})
        st.rerun()

    with st.chat_message("assistant", avatar=AVATAR["assistant"]):
        try:
            settings.validate()
            with st.spinner("Buscando en los documentos…"):
                resp, partes = responder_en_vivo(conv["mensajes"][-1]["texto"])
            st.write_stream(partes)
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
                {
                    "rol": "assistant",
                    "texto": "No pude generar la respuesta. Probá de nuevo en unos segundos.",
                    "detalle": str(e)[:300],
                    "error": True,
                    "fuentes": [],
                }
            )
    # Re-render para mostrar fuentes y feedback debajo de la respuesta ya escrita.
    st.rerun()


def modelo_activo() -> str:
    if settings.provider == "openai":
        return settings.openai_chat_model
    return settings.gemini_chat_model


# --------------------------------------------------------------------------
#  Barra lateral: marca + lista de conversaciones + estado
# --------------------------------------------------------------------------
with st.sidebar:
    st.markdown("<div class='marca-lateral'>TechRet<span class='ai'>AI</span></div>", unsafe_allow_html=True)
    st.caption("Asistente corporativo de TechRetail Solutions")

    if st.button("Nueva conversación", icon=":material/add:", use_container_width=True):
        ir_a_nueva()
        st.rerun()

    st.markdown("**Conversaciones**")

    # Solo se listan las conversaciones que ya tienen contenido (más recientes primero).
    listadas = [
        cid for cid in reversed(list(st.session_state.conversaciones.keys()))
        if st.session_state.conversaciones[cid]["mensajes"]
    ]

    if not listadas:
        st.caption("Todavía no hay conversaciones. Elegí una pregunta sugerida o escribí la tuya.")

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
            if c1.button("Guardar", key=f"save_{cid}", type="primary", use_container_width=True):
                conv["titulo"] = nuevo.strip() or conv["titulo"]
                st.session_state.renombrando = None
                st.rerun()
            if c2.button("Cancelar", key=f"cancel_{cid}", use_container_width=True):
                st.session_state.renombrando = None
                st.rerun()
        else:
            # Fila normal: seleccionar | renombrar | eliminar.
            sel, ren, dele = st.columns([0.68, 0.16, 0.16], gap="small", vertical_alignment="center")
            if sel.button(
                conv["titulo"], key=f"conv_{cid}", use_container_width=True,
                type="primary" if activa else "secondary", help=conv["titulo"],
            ):
                st.session_state.conv_actual = cid
                st.rerun()
            if ren.button("Renombrar", key=f"ed_{cid}", icon=":material/edit:", help="Renombrar"):
                st.session_state.renombrando = cid
                st.rerun()
            if dele.button("Eliminar", key=f"del_{cid}", icon=":material/delete:", help="Eliminar"):
                eliminar(cid)
                st.rerun()

    st.divider()
    st.markdown("**Estado**")
    st.caption(f"Modelo: `{modelo_activo()}`")
    try:
        st.caption(f"Base de conocimiento: **{vectorstore.stats()['fragmentos']}** fragmentos indexados")
    except Exception:
        st.caption("Base de conocimiento: no inicializada")

    st.divider()
    st.caption(
        ":material/info: Estás conversando con un **agente de IA**. Las respuestas se "
        "basan en documentos internos y pueden contener errores: verificá en la fuente citada."
    )


# --------------------------------------------------------------------------
#  Encabezado + conversación activa
# --------------------------------------------------------------------------
st.markdown(
    "<div class='marca'>TechRet<span class='ai'>AI</span></div>"
    "<div class='subt'>Preguntá lo que necesites sobre la documentación interna de la empresa.</div>",
    unsafe_allow_html=True,
)

conv = conv_actual()

# Las sugerencias viven en un único espacio reservado: al empezar la conversación
# se vacía en el acto. Sin esto, Streamlit sigue mostrando las tarjetas del render
# anterior (atenuadas) mientras se genera la primera respuesta.
inicio = st.empty()

if conv["mensajes"]:
    inicio.empty()
    # Si la conversación fue renombrada, su título completo (que en la barra lateral
    # puede verse recortado) no aparece en el chat: se muestra acá.
    if conv["titulo"] != conv["mensajes"][0]["texto"][:120]:
        st.caption(f":material/forum: {conv['titulo']}")
else:
    with inicio.container():
        st.markdown("<div class='seccion'>Probá con una de estas preguntas</div>", unsafe_allow_html=True)
        # Fila por fila, para que las tarjetas de cada fila queden alineadas.
        for fila in range(0, len(EJEMPLOS), 2):
            cols = st.columns(2)
            for col, (i, (icono, ejemplo)) in zip(cols, enumerate(EJEMPLOS[fila:fila + 2], start=fila)):
                if col.button(ejemplo, key=f"ej_{i}", icon=icono, use_container_width=True):
                    procesar(ejemplo)

for i, msg in enumerate(conv["mensajes"]):
    with st.chat_message(msg["rol"], avatar=AVATAR[msg["rol"]]):
        if msg.get("error"):
            st.error(msg["texto"], icon=":material/error:")
            if msg.get("detalle"):
                st.caption(f"Detalle técnico: {msg['detalle']}")
        elif msg.get("aviso"):
            st.info(msg["texto"], icon=":material/hourglass_top:")
        else:
            st.markdown(msg["texto"])
        if msg.get("fuentes"):
            with st.expander("Fuentes citadas", icon=":material/description:"):
                filas = []
                for f in msg["fuentes"]:
                    clase, etiqueta = nivel_relevancia(f["relevancia"])
                    categoria = CATEGORIAS.get(f["categoria"], f["categoria"])
                    filas.append(
                        "<div class='fuente'>"
                        f"<span class='archivo'>{html.escape(f['archivo'])}</span>"
                        f"<span class='meta'>{html.escape(categoria)} · {html.escape(f['formato'].upper())}</span>"
                        f"<span class='nivel {clase}' title='Similitud {f['relevancia']:.2f}'>{etiqueta}</span>"
                        "</div>"
                    )
                st.markdown("".join(filas), unsafe_allow_html=True)
        if msg["rol"] == "assistant" and msg.get("respuesta_obj"):
            if msg.get("feedback_dado"):
                # Confirmación explícita: un widget deshabilitado no deja ver qué se eligió.
                if msg.get("feedback") == "positivo":
                    st.caption(":material/thumb_up: Marcaste esta respuesta como útil. ¡Gracias!")
                else:
                    st.caption(":material/thumb_down: Marcaste esta respuesta como poco útil. Lo tendremos en cuenta.")
            else:
                cid = st.session_state.conv_actual
                valor = st.feedback("thumbs", key=f"fb_{cid}_{i}")
                if valor is not None:
                    msg["feedback"] = "positivo" if valor == 1 else "negativo"
                    registrar(msg["respuesta_obj"], feedback=msg["feedback"])
                    msg["feedback_dado"] = True
                    st.rerun()


# Si la última intervención es del usuario, la respuesta está pendiente de generarse.
pendiente = bool(conv["mensajes"]) and conv["mensajes"][-1]["rol"] == "user"

# El campo se dibuja antes de generar (siempre queda abajo) y se deshabilita
# mientras se escribe la respuesta, para no cortarla con otra pregunta.
pregunta = st.chat_input(
    "Escribí tu pregunta…",
    max_chars=settings.max_question_chars or None,
    disabled=pendiente,
)
if pregunta:
    procesar(pregunta)

if pendiente:
    responder_pendiente(conv)
