"""
Agente de atendimento via Groq tool calling.

Uso:
    from src.agent import Session, run_turn
    s = Session()
    print(run_turn(s, "Quanto custa o Takamine GD20?"))
    print(run_turn(s, "Tem em estoque?"))   # mantém contexto

O histórico é mantido na Session. run_turn faz um turno completo: envia
a mensagem, executa tool calls em loop até o LLM responder texto, e
adiciona a resposta final ao histórico.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from groq import APIError, APIStatusError, Groq, RateLimitError

from src import config
from src.prompts import SYSTEM_PROMPT, TOOL_MAP, TOOL_SCHEMAS

logger = logging.getLogger(__name__)

MAX_TOOL_ITERATIONS = 5
MAX_HISTORY_MESSAGES = 20


class AgentError(RuntimeError):
    """Erro amigável para o usuário final."""


@dataclass
class Session:
    """Estado de uma conversa com o agente."""

    messages: list[dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.messages:
            self.messages.append({"role": "system", "content": SYSTEM_PROMPT})

    def reset(self) -> None:
        self.messages = [{"role": "system", "content": SYSTEM_PROMPT}]


def get_client() -> Groq:
    config.validate_config(check_api_key=True)
    return Groq(api_key=config.GROQ_API_KEY)


def run_turn(
    session: Session,
    user_message: str,
    client: Groq | None = None,
) -> str:
    """
    Executa um turno completo: envia a mensagem, processa tool calls até o
    LLM responder texto, adiciona a resposta ao histórico e retorna.
    """
    if not user_message or not user_message.strip():
        raise AgentError("Mensagem vazia.")

    client = client or get_client()

    session.messages.append({"role": "user", "content": user_message.strip()})
    _trim_history(session)

    for iteration in range(MAX_TOOL_ITERATIONS + 1):
        try:
            response = client.chat.completions.create(
            model=config.GROQ_MODEL,
            messages=session.messages,
            tools=TOOL_SCHEMAS,
            tool_choice="auto",
            temperature=0.3,
            max_tokens=800,
            reasoning_effort="none",  # desativa thinking mode do Qwen 3.6
        )
        except RateLimitError as exc:
            logger.warning("Rate limit atingido: %s", exc)
            raise AgentError(
                "Tô com muitas solicitações no momento. Tenta de novo em "
                "alguns segundos, por favor."
            ) from exc
        except APIStatusError as exc:
            if getattr(exc, "status_code", None) == 413:
                logger.warning("Requisição grande demais (413): %s", exc)
                raise AgentError(
                    "A conversa ficou longa demais. Pode iniciar uma nova "
                    "conversa, por favor?"
                ) from exc
            logger.error("APIStatusError: %s", exc)
            raise AgentError(
                "Deu um erro ao falar com o serviço de IA. Tenta de novo em "
                "instantes."
            ) from exc
        except APIError as exc:
            logger.error("APIError: %s", exc)
            raise AgentError(
                "Não consegui processar sua mensagem agora. Tenta de novo em "
                "instantes."
            ) from exc

        if iteration == MAX_TOOL_ITERATIONS:
            raise AgentError(
                "Não consegui concluir a resposta em tempo. Pode reformular "
                "a pergunta?"
            )

        msg = response.choices[0].message
        tool_calls = getattr(msg, "tool_calls", None) or []

        # Sem tool calls: resposta final em texto.
        if not tool_calls:
            content = msg.content or ""
            if not content.strip():
                raise AgentError(
                    "Não consegui gerar uma resposta. Pode reformular?"
                )
            session.messages.append({"role": "assistant", "content": content})
            return content

        # Serializa a mensagem do assistant com os tool_calls.
        session.messages.append(
            {
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in tool_calls
                ],
            }
        )

        # Executa cada tool e adiciona o resultado ao histórico.
        for tc in tool_calls:
            name = tc.function.name
            raw_args = tc.function.arguments or "{}"

            try:
                args = json.loads(raw_args)
            except json.JSONDecodeError:
                logger.warning("Args inválidos para %s: %r", name, raw_args)
                result: dict = {
                    "error": "invalid_arguments",
                    "message": "Argumentos inválidos recebidos do LLM.",
                }
            else:
                fn = TOOL_MAP.get(name)
                if fn is None:
                    logger.warning("Tool desconhecida: %s", name)
                    result = {
                        "error": "unknown_tool",
                        "message": f"Ferramenta '{name}' não existe.",
                    }
                else:
                    try:
                        result = fn(**args)
                    except TypeError as exc:
                        logger.warning("Assinatura inválida %s(%s): %s", name, args, exc)
                        result = {
                            "error": "invalid_arguments",
                            "message": f"Argumentos incompatíveis para {name}: {exc}",
                        }
                    except Exception as exc:
                        logger.exception("Erro ao executar %s", name)
                        result = {
                            "error": "tool_failed",
                            "message": f"Falha ao executar {name}: {exc}",
                        }

            session.messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result, ensure_ascii=False),
                }
            )

    raise AgentError("Loop de tool calling esgotado sem resposta final.")


def _trim_history(session: Session, max_messages: int = MAX_HISTORY_MESSAGES) -> None:
    """
    Remove mensagens antigas mantendo:
    - o system prompt;
    - integridade entre assistant.tool_calls e as mensagens tool correspondentes.
    """
    messages = session.messages
    if len(messages) <= max_messages:
        return

    system = messages[0]
    body = messages[1:]
    trimmed = body[-(max_messages - 1):]

    # Não começa com tool message (o assistant correspondente foi cortado)
    while trimmed and trimmed[0].get("role") == "tool":
        trimmed = trimmed[1:]

    # Não começa com assistant que tem tool_calls (perdeu as respostas)
    while (
        trimmed
        and trimmed[0].get("role") == "assistant"
        and trimmed[0].get("tool_calls")
    ):
        trimmed = trimmed[1:]

    session.messages = [system] + trimmed