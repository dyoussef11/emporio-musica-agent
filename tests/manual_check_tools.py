"""
Script de verificação manual das ferramentas.

Roda as consultas principais de search_products e imprime os resultados
de forma legível. Não é pytest — é só um smoke test que dá para rodar
a qualquer momento durante o desenvolvimento.

Uso:
    python tests/manual_check_tools.py
"""

from src.tools import search_products


def check(title: str, **kwargs):
    print(f"\n=== {title} ===")
    r = search_products(**kwargs)
    print(f"count={r['count']}  truncated={r['truncated']}")
    for p in r["results"]:
        promo = f"  [{p['promotion']}]" if p["promotion"] else ""
        print(
            f"  {p['product_id']:>3}  {p['name']:<45}  "
            f"R$ {p['final_price_brl']:>8.2f}  estoque={p['stock_quantity']}{promo}"
        )


if __name__ == "__main__":
    # 1) Violões até R$ 1000 (cenário do enunciado)
    check("Violões até R$ 1000", category_id=5, max_price=1000, limit=10)

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