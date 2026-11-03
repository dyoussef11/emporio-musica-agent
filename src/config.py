"""
Configuração central do projeto.

Carrega variáveis de ambiente do .env, resolve caminhos relativos ao
projeto e valida que os arquivos de dados estão presentes.

Uso:
    from src import config
    config.GROQ_API_KEY
    config.PRODUCTS_CSV
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Raiz do projeto = pasta pai de src/
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent

# Carrega .env da raiz, se existir (silencioso se não existir)
load_dotenv(PROJECT_ROOT / ".env")

# ---- Variáveis de ambiente ----
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL: str = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b").strip()

DATA_DIR: Path = PROJECT_ROOT / os.getenv("DATA_DIR", "data")

# ---- Arquivos de dados ----
CATEGORIES_CSV: Path = DATA_DIR / "categories.csv"
CUSTOMERS_CSV: Path = DATA_DIR / "customers.csv"
ORDERS_CSV: Path = DATA_DIR / "orders.csv"
ORDER_ITEMS_CSV: Path = DATA_DIR / "order_items.csv"
PRODUCTS_CSV: Path = DATA_DIR / "products.csv"
PROMOTIONS_CSV: Path = DATA_DIR / "promotions.csv"
POLICIES_PDF: Path = DATA_DIR / "politicas_da_loja.pdf"

REQUIRED_FILES: tuple[Path, ...] = (
    CATEGORIES_CSV,
    CUSTOMERS_CSV,
    ORDERS_CSV,
    ORDER_ITEMS_CSV,
    PRODUCTS_CSV,
    PROMOTIONS_CSV,
    POLICIES_PDF,
)


class ConfigError(RuntimeError):
    """Erro de configuração do ambiente do projeto."""


def validate_config(check_api_key: bool = True) -> None:
    """
    Valida que o ambiente está pronto para rodar o agente.

    - Verifica se a chave do Groq está preenchida (opcional).
    - Verifica se todos os arquivos de dados existem.

    Levanta ConfigError com mensagem clara se algo faltar.
    """
    if check_api_key:
        if not GROQ_API_KEY:
            raise ConfigError(
                "GROQ_API_KEY não encontrada. Copie .env.example para .env "
                "e preencha com sua chave do Groq "
                "(https://console.groq.com/keys)."
            )
        if GROQ_API_KEY == "coloque_sua_chave_aqui":
            raise ConfigError(
                "GROQ_API_KEY ainda está com o placeholder do .env.example. "
                "Substitua pela chave real."
            )

    missing = [str(p) for p in REQUIRED_FILES if not p.exists()]
    if missing:
        raise ConfigError(
            "Arquivos de dados ausentes em data/:\n  - " + "\n  - ".join(missing)
        )