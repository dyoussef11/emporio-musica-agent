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

# --------------------------------------------------------------------- #
# get_order_status
# --------------------------------------------------------------------- #
def get_order_status(
    order_id: int,
    email: str | None = None,
    phone: str | None = None,
) -> dict[str, Any]:
    """
    Consulta o status de um pedido, com verificação leve de identidade.

    Regras:
    - Exige `order_id` + (`email` OU `phone`).
    - Se a verificação falhar, retorna o MESMO erro de "pedido não
      encontrado" — evita que a ferramenta sirva para descobrir se um
      `order_id` existe.
    - Retorna apenas o necessário: status, tracking, previsão, itens e
      um `next_step_hint` em PT-BR para o LLM usar como base.

    Retorno em sucesso:
        {
            "ok": True,
            "order": {
                "order_id": int,
                "status": str,                # valor cru do CSV
                "status_label": str,          # rótulo PT-BR
                "order_date": str | None,
                "total_brl": float,
                "payment_method": str,
                "tracking_code": str | None,
                "estimated_delivery": str | None,
                "notes": str | None,
                "items": [
                    {"product_id": int, "name": str, "quantity": int,
                     "unit_price_brl": float},
                    ...
                ],
                "customer_first_name": str | None,
                "next_step_hint": str,
            },
        }

    Retorno em falha:
        {
            "ok": False,
            "error": "verification_required" | "verification_failed",
            "message": str,
        }
    """
    store = get_store()

    has_email = bool(email and email.strip())
    has_phone = bool(phone and phone.strip())
    if not has_email and not has_phone:
        return {
            "ok": False,
            "error": "verification_required",
            "message": (
                "Para consultar o pedido, preciso do número do pedido e do "
                "e-mail OU telefone usado na compra."
            ),
        }

    order = store.get_order_by_id(order_id)
    if not order:
        return _verification_failed_response()

    customer = store.get_customer_by_id(int(order["customer_id"]))
    if not customer:
        return _verification_failed_response()

    email_ok = has_email and _emails_match(email or "", customer.get("email") or "")
    phone_ok = has_phone and _phones_match(phone or "", customer.get("phone") or "")

    if not (email_ok or phone_ok):
        return _verification_failed_response()

    items = _compact_order_items(order_id, store)
    customer_name = customer.get("name") or ""
    first_name = customer_name.split()[0] if customer_name else None

    return {
        "ok": True,
        "order": {
            "order_id": int(order["order_id"]),
            "status": str(order["status"]),
            "status_label": _status_label(str(order["status"])),
            "order_date": order.get("order_date"),
            "total_brl": float(order["total_brl"]),
            "payment_method": str(order["payment_method"]),
            "tracking_code": order.get("tracking_code"),
            "estimated_delivery": order.get("estimated_delivery"),
            "notes": order.get("notes"),
            "items": items,
            "customer_first_name": first_name,
            "next_step_hint": _next_step_hint(order),
        },
    }


# --------------------------------------------------------------------- #
# get_order_status — helpers
# --------------------------------------------------------------------- #
def _verification_failed_response() -> dict[str, Any]:
    return {
        "ok": False,
        "error": "verification_failed",
        "message": (
            "Não consegui localizar um pedido com esses dados. Confira o "
            "número do pedido e o e-mail ou telefone usados na compra."
        ),
    }


def _compact_order_items(
    order_id: int, store: DataStore
) -> list[dict[str, Any]]:
    items = store.get_order_items(order_id)
    compact: list[dict[str, Any]] = []
    for item in items:
        product = store.get_product_by_id(int(item["product_id"]))
        if not product:
            continue
        compact.append(
            {
                "product_id": int(product["product_id"]),
                "name": str(product["name"]),
                "quantity": int(item["quantity"]),
                "unit_price_brl": float(product["price_brl"]),
            }
        )
    return compact


def _emails_match(provided: str, stored: str) -> bool:
    return provided.strip().lower() == stored.strip().lower()


def _normalize_phone(phone: str) -> str:
    return "".join(ch for ch in phone if ch.isdigit())


def _phones_match(provided: str, stored: str) -> bool:
    a = _normalize_phone(provided)
    b = _normalize_phone(stored)
    if not a or not b:
        return False
    n = min(len(a), len(b), 11)
    return a[-n:] == b[-n:]


_STATUS_LABELS: dict[str, str] = {
    "pending": "aguardando confirmação de pagamento",
    "confirmed": "pagamento confirmado, aguardando despacho",
    "shipped": "despachado",
    "delivered": "entregue",
    "cancelled": "cancelado",
}


def _status_label(status: str) -> str:
    return _STATUS_LABELS.get(status, status)


def _next_step_hint(order: dict[str, Any]) -> str:
    """Nota interna em PT-BR para o LLM usar como base ao redigir a resposta."""
    status = str(order.get("status"))
    tracking = order.get("tracking_code")
    notes = order.get("notes")

    if status == "pending":
        return (
            "Pedido aguardando confirmação de pagamento. Oriente o cliente a "
            "verificar o método escolhido e, se já pagou, aguardar a "
            "compensação (boleto leva até 3 dias úteis)."
        )
    if status == "confirmed":
        return (
            "Pagamento confirmado, pedido em separação. O código de "
            "rastreamento será enviado por e-mail e WhatsApp assim que o "
            "pedido for despachado."
        )
    if status == "shipped":
        if tracking:
            return (
                f"Pedido despachado. Código de rastreamento: {tracking}. "
                "Pode ser consultado no site dos Correios ou da Jadlog."
            )
        return "Pedido despachado, código de rastreamento em processamento."
    if status == "delivered":
        return (
            "Pedido entregue. Se houver defeito de fabricação, o cliente tem "
            "até 30 dias corridos. Em compras online, o direito de "
            "arrependimento é de 7 dias corridos após o recebimento."
        )
    if status == "cancelled":
        detail = f" Motivo registrado: {notes}." if notes else ""
        return f"Pedido cancelado.{detail}"
    return "Status do pedido consultado com sucesso."


# --------------------------------------------------------------------- #
# Schema para o tool calling do Groq
# --------------------------------------------------------------------- #
GET_ORDER_STATUS_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "get_order_status",
        "description": (
            "Consulta o status de um pedido, incluindo rastreamento, previsão "
            "de entrega e itens. Use quando o cliente perguntar sobre o "
            "andamento de um pedido. REQUER o número do pedido E o e-mail OU "
            "telefone usados na compra. Se o cliente ainda não informou, "
            "pergunte antes de chamar a ferramenta. Nunca invente dados de "
            "pedido."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {
                    "type": "integer",
                    "description": "Número do pedido informado pelo cliente.",
                },
                "email": {
                    "type": "string",
                    "description": "E-mail usado na compra (opcional se tiver telefone).",
                },
                "phone": {
                    "type": "string",
                    "description": "Telefone usado na compra (opcional se tiver e-mail).",
                },
            },
            "required": ["order_id"],
        },
    },
}