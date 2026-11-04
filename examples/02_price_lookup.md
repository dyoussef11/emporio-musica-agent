# Price lookup — single product by name

**Date:** 2026-11-03  
**Model:** `qwen/qwen3.8-27b` (Groq)  
**Interface:** CLI (`python -m src.main --message "..."`)

## Conversation

**User:** Quanto custa o Takamine GD20?

**Agent:** O Takamine GD20 Dreadnought Natural tá saindo por **R$ 2.199,00**, com 5 unidades em estoque. Quer que eu te conte mais sobre ele ou te ajude com algo mais? 🎸

## Tools called

- `search_products(query="Takamine GD20")` → `count=1` (product_id 95, price 2199.00, stock 5, no active promotion)

## Takeaway

The agent used the product name as a free-text query, got exactly one result, and answered with price and stock. It did **not** invent specs or description — those weren't in the compact tool payload, and the agent didn't try to guess them.