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
│   ├── tools.py              # Tools: search_products, get_order_status, get_active_promotions get_order_status)
│   ├── prompts.py            # System prompt + tool schemas + tool map
│   ├── agent.py              # Tool-calling loop (Groq) + Session
│   └── main.py               # CLI (one-shot + REPL)
├── app.py                    # (TBD) Streamlit chat UI
├── examples/                 # Example conversations (challenge requirement)
└── tests/
    ├── manual_check_tools.py # Smoke tests for tools
    └── test_tools.py         # (TBD) pytest suite
    
```

## How to install

### You need first install `UV`:

### Linux/MacOs
```
curl -LsSf https://astral.sh/uv/install.sh | sh
```
or
```
brew install uv
```


### Windows
```
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

or 

```
winget install --id=astral-sh.uv -e
```

### Python (pip)

```
pip install uv
```
### After this, use this command: 

```
uv sync --extra dev
```

### Set `GROQ_API_KEY` in `.env` (see Setup above). Then:

#### CLI

```bash
# Interactive REPL
python -m src.main

# One-shot message
python -m src.main --message "Quanto custa o Takamine GD20?"

# Verbose (shows tool calls in the log)
python -m src.main --verbose
```

## Technical decisions

### Active promotions only — never offer an expired discount

`get_active_promotions` filters strictly on `is_active = 1` from
`promotions.csv`. The source file has 25 promotions but only **4** are
active at any given time (product IDs 127, 121, 90, 94 at the time of
writing). This is deliberate: the store policy says *"nunca prometer um
desconto que não está mais vigente"*, and offering an expired campaign is
the kind of mistake that triggers customer complaints.

The tool also filters out promoted products that are `discontinued` or
`out of stock` — a discounted product that can't be sold is misleading.

Return payload includes a business-rule `note` reminding the LLM that
**promotions are not cumulative** and that the **PIX 5% discount does not
apply over promotional prices**. This lets the model enforce the policy in
prose without another tool call.


### System prompt language and structure

The `SYSTEM_PROMPT` is written in **Portuguese** on purpose: the target
customer writes in PT-BR, the source policy PDF is in PT-BR, and a
PT-BR prompt keeps the LLM in the correct tone and idiom. The README and
code comments are in English because the evaluation context
(Artefact's email: *"All responses must be in English!"*) is in English
— but the **agent's output language is the customer's language**.

The prompt is organized in fixed sections (persona, scope, tools,
critical rules, business rules, guardrails, examples). This makes it
easy to audit against the store's manual (sections 7.1, 7.2, 7.3) and
easy to extend. Example dialogues are included to anchor tone and to
demonstrate the tool-calling flow — they function as lightweight few-shot
examples without burning tokens on real demonstration calls.

### Tool-calling loop and error handling

`run_turn(session, message)` runs one full turn: appends the user message,
calls the LLM with all tool schemas, executes any tool calls the model
requests, and loops until the model produces a final text response.

Deliberate guards:

- **`MAX_TOOL_ITERATIONS = 5`.** Prevents runaway loops (each iteration
  consumes free-tier quota). On the 5th iteration without a final answer,
  the agent raises a friendly `AgentError` asking the user to rephrase.
- **Serialization of `tool_calls` into plain dicts** before appending to
  history. The Groq SDK returns pydantic objects; converting to `dict`
  keeps `session.messages` JSON-serializable (useful for debugging and,
  later, persistence).
- **Per-error handling.** `RateLimitError` → "try again in a few seconds".
  `APIStatusError 413` (request too large) → "start a new conversation",
  since it's almost always long history. Generic `APIError` → neutral
  message. Each case is distinct because the user-facing advice differs.
- **Tool errors are results, not exceptions.** Invalid arguments from the
  LLM, unknown tool names, `TypeError` on the tool signature, or an
  unexpected exception inside a tool are all returned as
  `{"error": "...", "message": "..."}` in the `tool` message. The loop
  continues and the LLM gets a chance to fix its own call. This mirrors
  what production agents do: keep the conversation alive, let the model
  self-correct.
- **`temperature=0.3`, `max_tokens=800`.** Consistency over creativity for
  customer service; 800 tokens is plenty for a WhatsApp-style reply.
- **`MAX_HISTORY_MESSAGES = 20` with a tool-aware trim.** When history
  grows past 20 messages, the oldest are dropped — but never in the middle
  of an `assistant.tool_calls → tool` sequence (which would break the API
  contract). This is a defensive guard against the free-tier request-size
  limit, not a full memory-management solution (see "What I would do with
  more time").

## Known limitation

**Known limitation — ranking is not perfect.** TF-IDF on a short
Portuguese document with repeated domain vocabulary is prone to
false positives: e.g. "posso devolver um produto?" ranks a section
about discontinued products above the actual returns section, because
"devolver"/"devolução" occurs in both. Empirically, the correct chunk
appears in the **top 4** for every query tested in
`tests/manual_check_tools.py`. The system prompt therefore instructs
the LLM to read all returned chunks and select the one that actually
answers the question, rather than automatically trusting chunk #1.
- The agent does **not** compute date arithmetic on order status. If a
  customer asks "can I return order 1?" and that order was delivered over
  a year ago, the agent confirms the 7-day window rule from the policy
  but does not calculate that the window has expired — it asks the
  customer for the delivery date instead. A production version should
  compare `estimated_delivery` against `today` and enforce the window
  automatically.

  