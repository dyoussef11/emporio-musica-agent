"""
Script de verificação manual das ferramentas.

Roda as consultas principais de search_products e imprime os resultados
de forma legível. Não é pytest — é só um smoke test que dá para rodar
a qualquer momento durante o desenvolvimento.

Uso:
    python tests/manual_check_tools.py
"""

from src.tools import search_products
from src.tools import get_order_status


def check(title: str, **kwargs):
    print(f"\n=== {title} ===")
    r = search_products(**kwargs)
    print(f"count={r['count']}  truncated={r['truncated']}")
    for p in r["results"]:
        promo = f"  [{p['promotion']}]" if p["promotion"] else ""
        print(
            f"  {p['product_id']:>3}  {p['name']:<45}  "
            f"$ {p['final_price_brl']:>8.2f}  estoque={p['stock_quantity']}{promo}"
        )



def check_order(title: str, **kwargs):
    print(f"\n=== {title} ===")
    r = get_order_status(**kwargs)
    print(f"ok={r.get('ok')}")
    if not r.get("ok"):
        print(f"error={r.get('error')}  msg={r.get('message')}")
        return
    o = r["order"]
    print(f"  status: {o['status_label']}  ({o['status']})")
    print(f"  data: {o['order_date']}  total: $ {o['total_brl']:.2f}  pagto: {o['payment_method']}")
    print(f"  tracking: {o['tracking_code']}  previsão: {o['estimated_delivery']}")
    print(f"  cliente: {o['customer_first_name']}")
    for it in o["items"]:
        print(f"    - {it['quantity']}x {it['name']}  $ {it['unit_price_brl']:.2f}")
    print(f"  hint: {o['next_step_hint']}")


if __name__ == "__main__":
    # 1) Violões até $ 1000 (cenário do enunciado)
    check("Violões até $ 1000", category_id=5, max_price=1000, limit=10)

    # 2) Busca por nome + promoção ativa
    check("Taylor", query="taylor")
    check("Kalani", query="kalani")
    check("Takamine", query="takamine")

    # 3) Produto sem estoque (96 = Giannini GF-3D, stock 0)
    check("Giannini GF-3D (padrão)", query="Giannini GF-3D")
    check(
        "Giannini GF-3D (in_stock_only=False)",
        query="Giannini GF-3D",
        in_stock_only=False,
    )

    # 4) Descontinuado (113 = Shelby SN-7C)
    check("Shelby SN-7C (padrão)", query="Shelby SN-7C")
    check(
        "Shelby SN-7C (incluindo descontinuados)",
        query="Shelby SN-7C",
        include_discontinued=True,
        in_stock_only=False,
    )
    
    # 5) Order status — cenários de verificação e status variados
    #    Order 1: customer 3 (Pedro Henrique Oliveira), email pedro.oliveira@jmail.com,
    #    phone (67) 98432-1098, status delivered, tracking BRAB1234567BR.
    check_order("Order 1 — e-mail correto", order_id=1, email="pedro.oliveira@jmail.com")
    check_order("Order 1 — telefone correto", order_id=1, phone="(67) 98432-1098")
    check_order("Order 1 — telefone sem formatação", order_id=1, phone="67984321098")
    check_order("Order 1 — e-mail errado", order_id=1, email="invasor@x.com")
    check_order("Order 1 — sem credenciais", order_id=1)
    check_order("Order 999 — não existe", order_id=999, email="pedro.oliveira@jmail.com")

    # Order 10: customer 11 (Bruno Carvalho Martins), status confirmed, sem tracking
    check_order("Order 10 — confirmed sem tracking", order_id=10, email="bruno.martins@jmail.com")

    # Order 17: cancelled, notes "Pedido cancelado pelo cliente antes do processamento"
    # customer 15 (Matheus Ramos Correia)
    check_order("Order 17 — cancelled com notas", order_id=17, email="matheus.correia@hayoo.com.br")