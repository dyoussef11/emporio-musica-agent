"""
CLI do agente.

Uso:
    python -m src.main                          # REPL interativo
    python -m src.main --message "olá"          # one-shot
    python -m src.main --verbose                # ativa logs de debug

Comandos no REPL:
    /reset    limpa o histórico da conversa
    /sair     encerra
    /ajuda    lista comandos
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

from src.agent import AgentError, Session, run_turn
from src.config import validate_config


def _enable_ansi_on_windows() -> None:
    """Habilita sequências ANSI no terminal do Windows (Win10+)."""
    if os.name == "nt":
        os.system("")


# Códigos ANSI simples, sem dependência externa
_BOLD = "\033[1m"
_DIM = "\033[2m"
_CYAN = "\033[36m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_RED = "\033[31m"
_RESET = "\033[0m"


def _print_agent(text: str) -> None:
    print(f"{_GREEN}{_BOLD}Agente:{_RESET} {text}\n")


def _print_info(text: str) -> None:
    print(f"{_DIM}{text}{_RESET}")


def _print_error(text: str) -> None:
    print(f"{_RED}{text}{_RESET}", file=sys.stderr)


def one_shot(message: str) -> int:
    """Executa um único turno e imprime a resposta."""
    session = Session()
    try:
        reply = run_turn(session, message)
    except AgentError as exc:
        _print_error(f"[erro] {exc}")
        return 1
    _print_agent(reply)
    return 0


def repl() -> int:
    """REPL interativo até o usuário sair."""
    session = Session()
    _print_info(
        "Empório da Música — assistente virtual\n"
        "Digite sua mensagem. Comandos: /reset, /sair, /ajuda\n"
    )

    while True:
        try:
            raw = input(f"{_CYAN}{_BOLD}Você:{_RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            _print_info("Até logo!")
            return 0

        if not raw:
            continue

        if raw.startswith("/"):
            cmd = raw.lower()
            if cmd in ("/sair", "/exit", "/quit"):
                _print_info("Até logo!")
                return 0
            if cmd == "/reset":
                session.reset()
                _print_info("Histórico limpo.")
                continue
            if cmd in ("/ajuda", "/help"):
                _print_info(
                    "Comandos disponíveis:\n"
                    "  /reset  limpa o histórico da conversa\n"
                    "  /sair   encerra o CLI\n"
                    "  /ajuda  mostra esta mensagem\n"
                )
                continue
            _print_error(f"Comando desconhecido: {raw}")
            continue

        try:
            reply = run_turn(session, raw)
        except AgentError as exc:
            _print_error(f"[erro] {exc}")
            continue
        _print_agent(reply)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="src.main",
        description="CLI do agente da Empório da Música.",
    )
    parser.add_argument(
        "-m",
        "--message",
        help="Envia uma única mensagem e imprime a resposta (one-shot).",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Ativa logging de debug (mostra tool calls).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    _enable_ansi_on_windows()
    args = build_parser().parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        validate_config(check_api_key=True)
    except Exception as exc:
        _print_error(f"[config] {exc}")
        return 2

    if args.message:
        return one_shot(args.message)
    return repl()


if __name__ == "__main__":
    raise SystemExit(main())