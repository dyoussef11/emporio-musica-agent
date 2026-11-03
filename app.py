"""
Interface Streamlit do agente da Empório da Música.

Uso:
    streamlit run app.py
"""

from __future__ import annotations

import streamlit as st

from src import config
from src.agent import AgentError, Session, run_turn

# --------------------------------------------------------------------- #
# Configuração da página
# --------------------------------------------------------------------- #
st.set_page_config(
    page_title="Empório da Música — Atendimento",
    page_icon="🎸",
    layout="centered",
    initial_sidebar_state="expanded",
)

# --------------------------------------------------------------------- #
# Validação de ambiente (antes de renderizar qualquer coisa)
# --------------------------------------------------------------------- #
try:
    config.validate_config(check_api_key=True)
except Exception as exc:
    st.error(f"⚠️ Problema de configuração: {exc}")
    st.stop()

# Pré-carrega o índice de políticas para não travar na primeira pergunta
from src.policy_rag import get_policy_index
try:
    with st.spinner("Carregando manual de políticas..."):
        get_policy_index()
except Exception as exc:
    st.warning(f"Não foi possível carregar o manual de políticas: {exc}")
# --------------------------------------------------------------------- #
# Estado da conversa
# --------------------------------------------------------------------- #
if "agent_session" not in st.session_state:
    st.session_state.agent_session = Session()

if "display_history" not in st.session_state:
    # Histórico só para renderizar: role, content, tool_calls (opcional)
    st.session_state.display_history = []

if "show_tools" not in st.session_state:
    st.session_state.show_tools = False


def _extract_new_tool_calls(session: Session, since: int) -> list[dict]:
    """Coleta tool_calls adicionados em session.messages[since:]."""
    calls: list[dict] = []
    for msg in session.messages[since:]:
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                calls.append(
                    {
                        "name": tc["function"]["name"],
                        "arguments": tc["function"]["arguments"],
                    }
                )
    return calls


# --------------------------------------------------------------------- #
# Sidebar
# --------------------------------------------------------------------- #
with st.sidebar:
    st.title("🎸 Empório da Música")
    st.caption("Atendimento virtual")

    if st.button("🔄 Nova conversa", use_container_width=True):
        st.session_state.agent_session = Session()
        st.session_state.display_history = []
        st.rerun()

    st.divider()

    st.toggle(
        "🔧 Mostrar tool calls",
        key="show_tools",
        help="Exibe as consultas feitas ao catálogo, pedidos e manual de políticas.",
    )

    st.divider()
    st.caption(f"**Modelo:** `{config.GROQ_MODEL}`")
    st.caption("Desafio técnico — Artefact AI Engineer")


# --------------------------------------------------------------------- #
# Área principal
# --------------------------------------------------------------------- #
st.title("Atendimento")
st.caption(
    "Pergunte sobre instrumentos, preços, pedidos, políticas da loja "
    "ou peça uma recomendação. Respondo em português. 🎶"
)

# Renderiza o histórico
for entry in st.session_state.display_history:
    with st.chat_message(entry["role"], avatar="🎸" if entry["role"] == "assistant" else None):
        st.markdown(entry["content"])
        tool_calls = entry.get("tool_calls") or []
        if tool_calls:
            with st.expander(f"🔧 {len(tool_calls)} consulta(s) ao sistema"):
                for tc in tool_calls:
                    st.code(f"{tc['name']}({tc['arguments']})", language="python")

# Chat input
prompt = st.chat_input("Digite sua mensagem...")
if prompt:
    # Mostra mensagem do usuário
    with st.chat_message("user"):
        st.markdown(prompt)
    st.session_state.display_history.append(
        {"role": "user", "content": prompt}
    )

    # Turno do agente
    with st.chat_message("assistant", avatar="🎸"):
        prev_len = len(st.session_state.agent_session.messages)
        with st.spinner("Consultando..."):
            try:
                reply = run_turn(st.session_state.agent_session, prompt)
                tool_calls = _extract_new_tool_calls(
                    st.session_state.agent_session, prev_len
                )

                st.markdown(reply)

                if tool_calls and st.session_state.show_tools:
                    with st.expander(f"🔧 {len(tool_calls)} consulta(s) ao sistema"):
                        for tc in tool_calls:
                            st.code(
                                f"{tc['name']}({tc['arguments']})",
                                language="python",
                            )

                st.session_state.display_history.append(
                    {
                        "role": "assistant",
                        "content": reply,
                        "tool_calls": tool_calls if st.session_state.show_tools else [],
                    }
                )
            except AgentError as exc:
                error_msg = f"⚠️ {exc}"
                st.error(error_msg)
                st.session_state.display_history.append(
                    {"role": "assistant", "content": error_msg}
                )