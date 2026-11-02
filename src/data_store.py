"""
Camada de acesso aos dados do desafio.

Carrega os CSVs com Pandas uma única vez (singleton via get_store()),
normaliza tipos e expõe funções pequenas e tipadas para que as ferramentas
(src/tools.py) não precisem conhecer detalhes do Pandas.

Decisões:
- CSVs em vez de SQLite: o volume é pequeno (< 100 linhas por tabela),
  e a leitura direta com Pandas é mais simples de auditar e explicar.
- Parse do campo `specs` (JSON em string) na carga: assim as ferramentas
  recebem dicionário pronto, não string.
- Acessores retornam dicionários Python puros (não Series), para que o
  resultado seja direto de serializar em JSON quando for enviado ao LLM.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

import pandas as pd

from src import config


class DataStore:
    """Container imutável dos dados do desafio."""

    def __init__(self) -> None:
        config.validate_config(check_api_key=False)

        self.categories: pd.DataFrame = pd.read_csv(config.CATEGORIES_CSV)
        self.customers: pd.DataFrame = pd.read_csv(config.CUSTOMERS_CSV)
        self.orders: pd.DataFrame = pd.read_csv(
            config.ORDERS_CSV,
            parse_dates=["order_date", "estimated_delivery"],
        )
        self.order_items: pd.DataFrame = pd.read_csv(config.ORDER_ITEMS_CSV)
        self.products: pd.DataFrame = pd.read_csv(
            config.PRODUCTS_CSV,
            parse_dates=["created_at"],
        )
        self.promotions: pd.DataFrame = pd.read_csv(config.PROMOTIONS_CSV)

        # Parse do campo specs (JSON em string) -> dicionário
        self.products["specs_parsed"] = self.products["specs"].apply(_parse_specs)

    # ------------------------------------------------------------------ #
    # Produtos
    # ------------------------------------------------------------------ #
    def get_product_by_id(self, product_id: int) -> dict[str, Any] | None:
        row = self.products.loc[self.products["product_id"] == product_id]
        return _row_to_dict(row.iloc[0]) if not row.empty else None

    def find_products_by_name(self, fragment: str) -> list[dict[str, Any]]:
        fragment = fragment.strip().lower()
        if not fragment:
            return []
        mask = self.products["name"].str.lower().str.contains(fragment, regex=False)
        return [_row_to_dict(r) for _, r in self.products[mask].iterrows()]

    def get_active_promotion_for_product(
        self, product_id: int
    ) -> dict[str, Any] | None:
        mask = (self.promotions["product_id"] == product_id) & (
            self.promotions["is_active"] == 1
        )
        row = self.promotions[mask]
        return _row_to_dict(row.iloc[0]) if not row.empty else None

    def get_all_active_promotions(self) -> list[dict[str, Any]]:
        active = self.promotions[self.promotions["is_active"] == 1]
        return [_row_to_dict(r) for _, r in active.iterrows()]

    # ------------------------------------------------------------------ #
    # Categorias
    # ------------------------------------------------------------------ #
    def get_category_name(self, category_id: int) -> str | None:
        row = self.categories.loc[self.categories["category_id"] == category_id]
        return str(row.iloc[0]["name"]) if not row.empty else None

    # ------------------------------------------------------------------ #
    # Pedidos e clientes
    # ------------------------------------------------------------------ #
    def get_order_by_id(self, order_id: int) -> dict[str, Any] | None:
        row = self.orders.loc[self.orders["order_id"] == order_id]
        return _row_to_dict(row.iloc[0]) if not row.empty else None

    def get_customer_by_email(self, email: str) -> dict[str, Any] | None:
        email = email.strip().lower()
        mask = self.customers["email"].str.lower() == email
        row = self.customers[mask]
        return _row_to_dict(row.iloc[0]) if not row.empty else None

    def get_customer_by_id(self, customer_id: int) -> dict[str, Any] | None:
        row = self.customers.loc[self.customers["customer_id"] == customer_id]
        return _row_to_dict(row.iloc[0]) if not row.empty else None

    def get_order_items(self, order_id: int) -> list[dict[str, Any]]:
        items = self.order_items[self.order_items["order_id"] == order_id]
        return [_row_to_dict(r) for _, r in items.iterrows()]


# ---------------------------------------------------------------------- #
# Helpers internos
# ---------------------------------------------------------------------- #
def _parse_specs(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def _row_to_dict(row: pd.Series) -> dict[str, Any]:
    """Converte uma linha em dict Python puro, tratando NaN e datas."""
    result: dict[str, Any] = {}
    for key, value in row.items():
        if pd.isna(value):
            result[key] = None
        elif isinstance(value, pd.Timestamp):
            result[key] = value.strftime("%Y-%m-%d")
        else:
            result[key] = value
    return result


# ---------------------------------------------------------------------- #
# Singleton
# ---------------------------------------------------------------------- #
@lru_cache(maxsize=1)
def get_store() -> DataStore:
    """Retorna a instância única do DataStore (carrega na primeira chamada)."""
    return DataStore()