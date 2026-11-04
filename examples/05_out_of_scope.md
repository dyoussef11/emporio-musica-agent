# Out-of-scope request — accessory redirect

**Date:** 2026-11-03  
**Model:** `qwen/qwen3.8-27b` (Groq)  
**Interface:** CLI (`python -m src.main --message "..."`)

## Conversation

**User:** Vocês vendem cordas de violão?

**Agent:** A gente trabalha só com instrumentos musicais, não com acessórios como cordas, palhetas ou cabos. Mas se for um violão, tô aqui pra ajudar! 🎸

## Tools called

- `search_policies(query="escopo acessórios")` → 4 chunks; top hit was page 2, section 1: *"Trabalhamos exclusivamente com instrumentos musicais — não comercializamos acessórios como cordas, palhetas, cabos, cases, pedais ou amplificadores."*

## Takeaway

The agent found the scope rule in the manual and applied it — instead of hallucinating a "yes" or "no". It also redirected the conversation back to the store's actual offering (guitars), which is a useful recovery pattern for out-of-scope requests.