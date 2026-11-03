"""
Testes unitários das ferramentas do agente.

Rodar:
    pytest                    # todos
    pytest -v                 # verbose
    pytest tests/test_tools.py::test_search_products_category_and_price  # um só
"""

from __future__ import annotations

import pytest

from src.data_store import get_store
from src.policy_rag import get_policy_index
from src.tools import (
    get_active_promotions,
    get_order_status,
    search_policies,
    search_products,
)

# --------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def store():
    return get_store()


@pytest.fixture(scope="module")
def policy_index():
    return get_policy_index()


# --------------------------------------------------------------------- #
# search_products
# --------------------------------------------------------------------- #
def test_search_products_violoes_ate_1000(store):
    """Cenário do enunciado: violões até R$ 1000."""
    r = search_products(category_id=5, max_price=1000, limit=20)
    assert r["count"] > 0
    assert r["truncated"] is False  # limit=20 comporta todos
    for p in r["results"]:
        assert p["category"] == "Violões"
        assert p["price_brl"] <= 1000
        assert p["stock_quantity"] > 0
        assert p["status"] == "active"


def test_search_products_truncated_flag():
    """Quando há mais resultados que o limit, truncated=True."""
    r = search_products(category_id=5, max_price=1000, limit=3)
    assert r["count"] > 3
    assert r["truncated"] is True
    assert len(r["results"]) == 3


def test_search_products_ordered_by_price_ascending():
    r = search_products(category_id=5, max_price=1000, limit=20)
    prices = [p["price_brl"] for p in r["results"]]
    assert prices == sorted(prices)


def test_search_products_by_name():
    r = search_products(query="taylor", limit=10)
    assert r["count"] == 2
    names = [p["name"] for p in r["results"]]
    assert any("Taylor 110e" in n for n in names)
    assert any("Taylor 214ce" in n for n in names)


def test_search_products_promotion_applied():
    """Taylor 110e tem 8% off ativo — final_price_brl deve refletir o desconto."""
    r = search_products(query="Taylor 110e")
    assert r["count"] == 1
    p = r["results"][0]
    assert p["promotion"] is not None
    assert "8% off" in p["promotion"]
    assert p["final_price_brl"] < p["price_brl"]
    # 5999 * 0.92 = 5519.08
    assert abs(p["final_price_brl"] - 5519.08) < 0.01


def test_search_products_excludes_out_of_stock_by_default():
    """Giannini GF-3D (id 96) tem estoque 0 — some no modo padrão."""
    r = search_products(query="Giannini GF-3D")
    assert r["count"] == 0


def test_search_products_includes_out_of_stock_when_flagged():
    r = search_products(query="Giannini GF-3D", in_stock_only=False)
    assert r["count"] == 1
    assert r["results"][0]["product_id"] == 96


def test_search_products_excludes_discontinued_by_default():
    """Shelby SN-7C (id 113) está descontinuado."""
    r = search_products(query="Shelby SN-7C")
    assert r["count"] == 0


def test_search_products_includes_discontinued_when_flagged():
    r = search_products(
        query="Shelby SN-7C",
        include_discontinued=True,
        in_stock_only=False,
    )
    assert r["count"] == 1
    assert r["results"][0]["status"] == "discontinued"


def test_search_products_limit_clamped():
    """limit > MAX_LIMIT (20) é truncado silenciosamente para 20."""
    r = search_products(category_id=5, limit=999)
    assert len(r["results"]) <= 20


def test_search_products_min_price():
    r = search_products(category_id=5, min_price=2000, limit=20)
    assert all(p["price_brl"] >= 2000 for p in r["results"])


def test_search_products_coming_soon_excluded():
    """Kala KA-ABP-CTG (id 130) é coming_soon — não aparece em buscas."""
    r = search_products(query="Kala KA-ABP-CTG", in_stock_only=False)
    assert r["count"] == 0


# --------------------------------------------------------------------- #
# get_order_status
# --------------------------------------------------------------------- #
def test_get_order_status_with_email():
    r = get_order_status(order_id=1, email="pedro.oliveira@jmail.com")
    assert r["ok"] is True
    order = r["order"]
    assert order["order_id"] == 1
    assert order["status"] == "delivered"
    assert order["status_label"] == "entregue"
    assert order["tracking_code"] == "BRAB1234567BR"
    assert order["customer_first_name"] == "Pedro"
    assert len(order["items"]) == 1
    assert order["items"][0]["product_id"] == 93


def test_get_order_status_with_phone():
    r = get_order_status(order_id=1, phone="(67) 98432-1098")
    assert r["ok"] is True


@pytest.mark.parametrize(
    "phone",
    [
        "(67) 98432-1098",
        "67984321098",
        "+55 67 98432-1098",
        "67 98432-1098",
    ],
)
def test_get_order_status_phone_format_tolerance(phone):
    r = get_order_status(order_id=1, phone=phone)
    assert r["ok"] is True


def test_get_order_status_requires_credentials():
    r = get_order_status(order_id=1)
    assert r["ok"] is False
    assert r["error"] == "verification_required"


def test_get_order_status_wrong_email():
    r = get_order_status(order_id=1, email="invasor@example.com")
    assert r["ok"] is False
    assert r["error"] == "verification_failed"


def test_get_order_status_nonexistent_order_returns_same_error():
    """Não vaza se o order_id existe ou não."""
    r_missing = get_order_status(order_id=9999, email="pedro.oliveira@jmail.com")
    r_wrong = get_order_status(order_id=1, email="invasor@example.com")
    assert r_missing["error"] == r_wrong["error"] == "verification_failed"
    assert r_missing["message"] == r_wrong["message"]


def test_get_order_status_cancelled_includes_notes():
    """Order 17 está cancelado com notes explicando o motivo."""
    r = get_order_status(order_id=17, email="matheus.correia@hayoo.com.br")
    assert r["ok"] is True
    assert r["order"]["status"] == "cancelled"
    assert r["order"]["notes"] is not None
    assert "cancelado pelo cliente" in r["order"]["notes"].lower()
    assert "Motivo registrado" in r["order"]["next_step_hint"]


def test_get_order_status_confirmed_without_tracking():
    """Order 10 está confirmed e ainda não tem tracking."""
    r = get_order_status(order_id=10, email="bruno.martins@jmail.com")
    assert r["ok"] is True
    assert r["order"]["status"] == "confirmed"
    assert r["order"]["tracking_code"] is None


# --------------------------------------------------------------------- #
# get_active_promotions
# --------------------------------------------------------------------- #
def test_get_active_promotions_returns_only_active(store):
    r = get_active_promotions()
    assert r["count"] == len(store.get_all_active_promotions()) == 4
    product_ids = {p["product_id"] for p in r["results"]}
    assert product_ids == {90, 94, 121, 127}
    assert r["note"]  # nota sobre não cumulatividade e PIX


def test_get_active_promotions_sorted_by_discount_desc():
    r = get_active_promotions()
    discounts = [p["discount_percent"] for p in r["results"]]
    assert discounts == sorted(discounts, reverse=True)


def test_get_active_promotions_filter_ukuleles():
    r = get_active_promotions(category_id=9)
    assert r["count"] == 2
    for p in r["results"]:
        assert p["category"] == "Ukuleles"


def test_get_active_promotions_filter_violoes():
    r = get_active_promotions(category_id=5)
    assert r["count"] == 2
    for p in r["results"]:
        assert p["category"] == "Violões"


def test_get_active_promotions_filter_no_matches():
    """Categoria 2 (Baixos) não tem promoção ativa."""
    r = get_active_promotions(category_id=2)
    assert r["count"] == 0


def test_get_active_promotions_final_price_correct():
    """Taylor 110e: 5999 com 8% off = 5519.08."""
    r = get_active_promotions()
    taylor = next(p for p in r["results"] if p["product_id"] == 94)
    assert taylor["discount_percent"] == 8.0
    assert abs(taylor["final_price_brl"] - 5519.08) < 0.01


# --------------------------------------------------------------------- #
# search_policies
# --------------------------------------------------------------------- #
def test_search_policies_empty_query():
    r = search_policies(query="")
    assert r["count"] == 0
    assert "note" in r


def test_search_policies_pagamento():
    r = search_policies(query="formas de pagamento parcelamento")
    assert r["count"] >= 1
    # Top hit deve mencionar pagamento
    top = r["results"][0]["text"].lower()
    assert "pagamento" in top or "pix" in top or "cartão" in top or "parcelamento" in top


def test_search_policies_scope_acessorios():
    r = search_policies(query="vocês vendem acessórios como cordas")
    assert r["count"] >= 1
    # Deve encontrar o trecho do escopo (só instrumentos, não acessórios)
    joined = " ".join(hit["text"].lower() for hit in r["results"])
    assert "acessórios" in joined or "instrumentos musicais" in joined


def test_search_policies_garantia():
    r = search_policies(query="como funciona a garantia")
    assert r["count"] >= 1
    joined = " ".join(hit["text"].lower() for hit in r["results"])
    assert "garantia" in joined


def test_search_policies_top_k_clamped():
    """top_k > 5 é truncado para 5."""
    r = search_policies(query="garantia", top_k=99)
    assert len(r["results"]) <= 5


def test_search_policies_result_shape():
    r = search_policies(query="horário de funcionamento")
    for hit in r["results"]:
        assert "page" in hit
        assert "text" in hit
        assert "score" in hit
        assert isinstance(hit["page"], int)
        assert hit["page"] >= 1


# --------------------------------------------------------------------- #
# Integridade dos dados carregados
# --------------------------------------------------------------------- #
def test_store_loads_all_csvs(store):
    """Sanity check: os CSVs carregaram com tamanho esperado."""
    assert len(store.products) == 65
    assert len(store.orders) == 20
    assert len(store.customers) == 50
    assert len(store.categories) == 9

def test_store_specs_parsed_as_dict(store):
    """specs_parsed deve ser dict, não string."""
    p = store.get_product_by_id(95)
    assert isinstance(p["specs_parsed"], dict)
    assert p["specs_parsed"].get("top") == "Cedro Sólido"


def test_policy_index_has_chunks(policy_index):
    assert len(policy_index.chunks) > 0
    for chunk in policy_index.chunks:
        assert chunk.page >= 1
        assert len(chunk.text) >= 80