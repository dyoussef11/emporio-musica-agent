"""
Ferramentas que o agente LLM pode chamar via tool calling do Groq.

Cada ferramenta:
- Tem um schema JSON registrável no Groq (SEARCH_PRODUCTS_SCHEMA, etc.)
- É uma função pura que consulta o DataStore
- Retorna um dicionário pequeno e JSON-serializável, com poucos campos,
  para não estourar o limite de tokens do free tier do Groq
  (6.000 tokens por requisição em alguns modelos).
"""

from __future__ import annotations

from typing import Any

from src.data_store import DataStore, get_store

MAX_LIMIT = 20
DEFAULT_LIMIT = 5


# --------------------------------------------------------------------- #
# search_products
# --------------------------------------------------------------------- #
def search_products(
    query: str | None = None,
    category_id: int | None = None,
    max_price: float | None = None,
    min_price: float | None = None,
    in_stock_only: bool = True,
    include_discontinued: bool = False,
    limit: int = DEFAULT_LIMIT,
) -> dict[str, Any]:
    """
    Busca produtos por nome, categoria e faixa de preço.

    Retorna:
        {
            "count": int,       # total de produtos que casaram (antes do limit)
            "truncated": bool,  # True se count > limit
            "results": [ {produto compacto}, ... ],
        }
    """
    store = get_store()

    if limit < 1:
        limit = DEFAULT_LIMIT
    if limit > MAX_LIMIT:
        limit = MAX_LIMIT

    df = store.products.copy()

    # Filtro de status
    allowed_status = {"active"}
    if include_discontinued:
        allowed_status.add("discontinued")
    df = df[df["status"].isin(allowed_status)]

    # Filtro de nome (substring, case-insensitive)
    if query and query.strip():
        df = df[df["name"].str.lower().str.contains(query.strip().lower(), regex=False)]

    # Filtro de categoria
    if category_id is not None:
        df = df[df["category_id"] == category_id]

    # Faixa de preço
    if min_price is not None:
        df = df[df["price_brl"] >= min_price]
    if max_price is not None:
        df = df[df["price_brl"] <= max_price]

    # Estoque
    if in_stock_only:
        df = df[df["stock_quantity"] > 0]

    # Ordena por preço crescente (determinístico, útil para faixas de preço)
    df = df.sort_values("price_brl").reset_index(drop=True)

    total_count = int(len(df))
    truncated = total_count > limit
    df = df.head(limit)

    results = [_compact_product(row, store) for _, row in df.iterrows()]

    return {
        "count": total_count,
        "truncated": truncated,
        "results": results,
    }


# --------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------- #
def _compact_product(row: Any, store: DataStore) -> dict[str, Any]:
    """Reduz um produto ao essencial + promoção ativa, para economizar tokens."""
    product_id = int(row["product_id"])
    base_price = float(row["price_brl"])

    promo = store.get_active_promotion_for_product(product_id)
    if promo:
        discount = float(promo["discount_percent"])
        final_price = round(base_price * (1 - discount / 100.0), 2)
        promotion_text = f"{discount:.0f}% off - {promo['description']}"
    else:
        final_price = base_price
        promotion_text = None

    return {
        "product_id": product_id,
        "name": str(row["name"]),
        "price_brl": base_price,
        "final_price_brl": final_price,
        "promotion": promotion_text,
        "stock_quantity": int(row["stock_quantity"]),
        "status": str(row["status"]),
        "category": store.get_category_name(int(row["category_id"])),
    }


# --------------------------------------------------------------------- #
# Schema para o tool calling do Groq
# --------------------------------------------------------------------- #
SEARCH_PRODUCTS_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "search_products",
        "description": (
            "Busca produtos do catálogo da Empório da Música por nome, categoria "
            "e/ou faixa de preço. Use quando o cliente perguntar sobre "
            "disponibilidade, opções de instrumentos, preços ou alternativas. "
            "Retorna até 20 produtos com preço, estoque e promoção ativa. "
            "Categorias: 1=Guitarras, 2=Baixos, 3=Baterias/Percussão, "
            "4=Teclados/Pianos, 5=Violões, 6=Sopro Madeiras, 7=Sopro Metais, "
            "8=Cordas Orquestrais, 9=Ukuleles."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Trecho do nome do produto "
                        "(ex: 'Taylor', 'violão', 'ukulele tenor')."
                    ),
                },
                "category_id": {
                    "type": "integer",
                    "description": "ID da categoria (1 a 9). Ver descrição acima.",
                },
                "max_price": {
                    "type": "number",
                    "description": "Preço máximo em BRL (inclusive).",
                },
                "min_price": {
                    "type": "number",
                    "description": "Preço mínimo em BRL (inclusive).",
                },
                "in_stock_only": {
                    "type": "boolean",
                    "description": "Se True (padrão), só retorna produtos com estoque > 0.",
                    "default": True,
                },
                "include_discontinued": {
                    "type": "boolean",
                    "description": "Se True, inclui descontinuados. Padrão False.",
                    "default": False,
                },
                "limit": {
                    "type": "integer",
                    "description": "Máximo de produtos a retornar (padrão 5, máx 20).",
                    "default": 5,
                },
            },
            "required": [],
        },
    },
}