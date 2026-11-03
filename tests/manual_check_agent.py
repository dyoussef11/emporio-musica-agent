"""
Smoke test do agente contra o Groq.

⚠️  Consome quota do free tier. Rode uma vez por commit, no máximo.

Uso:
    python tests/manual_check_agent.py
    python tests/manual_check_agent.py "Quanto custa o Takamine GD20?"

Sem argumentos, roda 4 cenários mínimos.
"""

from __future__ import annotations

import sys

from src import config
from src.agent import AgentError, Session, run_turn


def one_shot(message: str) -> None:
    print(f"\n>>> {message}")
    session = Session()
    try:
        reply = run_turn(session, message)
        print(f"<<< {reply}")
    except AgentError as exc:
        print(f"[AgentError] {exc}")


if __name__ == "__main__":
    config.validate_config(check_api_key=True)

    if len(sys.argv) > 1:
        one_shot(" ".join(sys.argv[1:]))
    else:
        scenarios = [
            "Quanto custa o Takamine GD20?",
            "Quais violões disponíveis custando até R$ 1000?",
            "Vocês vendem cordas de violão?",
            (
                "Me arrependi de uma compra, posso devolver o pedido 1? "
                "Meu e-mail é pedro.oliveira@jmail.com"
            ),
        ]
        for s in scenarios:
            one_shot(s)