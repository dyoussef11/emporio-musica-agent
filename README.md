# Empório da Música — Customer Service Agent

A text-based customer service agent for **Empório da Música**, a fictional
musical instrument store in Campo Grande/MS, Brazil. Built as the technical
challenge for the **AI Engineer** role at [Artefact](https://www.artefact.com/).

> ⚠️ **Status: work in progress.** This README will be completed as the
> project evolves. Sections marked as `(TBD)` will be filled in the final
> commit.

---

## What the agent does

The agent receives text messages from customers and answers based on:

- **Structured data** in `data/*.csv` — products, categories, customers,
  orders, order items, promotions.
- **Store policies** in `data/politicas_da_loja.pdf` — opening hours,
  payment methods, returns, shipping, warranty, scope.

It decides **when** to query structured data (e.g. product price, order
status) versus when to consult policies (e.g. return rules, store hours),
and politely redirects out-of-scope requests (the store sells **only
musical instruments**, not accessories).

---

## Stack

| Component | Choice | Why |
|---|---|---|
| Language | Python 3.12.10 | Balance of stability and library support (pandas 3.x, Streamlit, scikit-learn) |
| LLM | Groq (free tier) | Supports tool calling, OpenAI-compatible SDK, no cost for a prototype |
| Default model | `llama-3.3-70b-versatile` | Good reasoning + tool calling within Groq free tier |
| Data layer | pandas | CSVs are small (<100 rows/table); no need for a database |
| Policy retrieval | scikit-learn TF-IDF | Local, free, no external embedding service needed |
| Interface | CLI + Streamlit | CLI for fast iteration; Streamlit for a visual demo |
| Packaging | `pyproject.toml` | Single source of truth for dependencies; makes `src` importable from anywhere |

---

## Project structure

```text
emporio-musica-agent/
├── pyproject.toml            # Project metadata + dependencies
├── README.md
├── .env.example              # Template for environment variables
├── .gitignore
├── data/                     # CSVs + policy PDF (from the challenge)
│   ├── categories.csv
│   ├── customers.csv
│   ├── orders.csv
│   ├── order_items.csv
│   ├── products.csv
│   ├── promotions.csv
│   └── politicas_da_loja.pdf
├── src/                      # Agent source code
│   ├── __init__.py
│   ├── config.py             # Env vars + path resolution
│   ├── data_store.py         # CSV loading + typed accessors
│   ├── policy_rag.py         # (TBD) TF-IDF retrieval over the PDF
│   ├── tools.py              # Tools the LLM can call
│   ├── prompts.py            # (TBD) System prompt
│   ├── agent.py              # (TBD) Tool-calling loop
│   └── main.py               # (TBD) CLI entrypoint
├── app.py                    # (TBD) Streamlit chat UI
├── examples/                 # Example conversations (challenge requirement)
└── tests/
    ├── manual_check_tools.py # Smoke tests for tools
    └── test_tools.py         # (TBD) pytest suite