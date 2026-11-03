

# Empório da Música — Customer Service Agent

A text-based customer service agent for **Empório da Música**, a fictional
musical instrument store in Campo Grande/MS, Brazil. Built as the technical
challenge for the **AI Engineer** role at [Artefact](https://www.artefact.com/).

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
| Default model | `qwen/qwen3.8-27b` | Tool-calling capable, 131K context, free tier on Groq. Alternatives: `openai/gpt-oss-120b`, `llama-3.3-70b-versatile` |
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
│   ├── policy_rag.py         # TF-IDF retrieval over the policy PDF
│   ├── tools.py              # Tools: search_products, get_order_status,
│   │                         #        get_active_promotions, search_policies
│   ├── prompts.py            # System prompt + tool schemas + tool map
│   ├── agent.py              # Tool-calling loop (Groq) + Session
│   └── main.py               # CLI (one-shot + REPL)
├── app.py                    # Streamlit chat UI
├── examples/                 # Example conversations (challenge requirement)
└── tests/
    ├── manual_check_tools.py # Smoke tests for tools
    ├── manual_check_agent.py # Manual smoke test for the full agent (uses Groq)
    └── test_tools.py         # pytest suite for tools and policy retrieval
```

---

## Setup

Requires **Python 3.12+**.

### Option A — uv (recommended)

[uv](https://docs.astral.sh/uv/) is a fast Python package manager.

Install uv:

```bash
# Linux / macOS
curl -LsSf https://astral.sh/uv/install.sh | sh
# or
brew install uv

# Windows
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
# or
winget install --id=astral-sh.uv -e
```

Then:

```bash
uv sync --extra dev
```

uv creates `.venv/`, installs the project in editable mode, and pulls
runtime + dev dependencies from `pyproject.toml`.

### Option B — pip + venv

```bash
python3.12 -m venv .venv
source .venv/bin/activate          # Linux/macOS
# .venv\Scripts\activate           # Windows
pip install -e ".[dev]"
```

### Configure the API key

```bash
cp .env.example .env
# Edit .env and set GROQ_API_KEY with your key from
# https://console.groq.com/keys
```

Optional: change `GROQ_MODEL` in `.env` if the default is unavailable in
your account (see "Default model" above).

### Verify the setup

```bash
python -c "from src import config; config.validate_config(); print('config ok')"
pytest -q
```

---

## How to run

### CLI

```bash
# Interactive REPL
python -m src.main

# One-shot message
python -m src.main --message "Quanto custa o Takamine GD20?"

# Verbose (shows tool calls in the log)
python -m src.main --verbose
```

REPL commands: `/reset` (clear history), `/sair` (exit), `/ajuda` (help).

### Streamlit

```bash
streamlit run app.py
```

Opens at `http://localhost:8501`. Sidebar toggle **"Mostrar tool calls"**
exposes the data queries behind each answer — useful for demos and
evaluation.

---

## Technical decisions

### Packaging: `pyproject.toml` instead of `requirements.txt`

Using a single `pyproject.toml` avoids dependency duplication and makes
the `src` package importable from anywhere inside the venv (`pip install -e .`).
This solved a `ModuleNotFoundError` when running scripts under `tests/`
directly — the script's parent folder is added to `sys.path`, not the
project root.

### Data layer: pandas over SQLite

The challenge data is small (65 products, 20 orders, 50 customers). Loading
the CSVs once into a `DataStore` singleton with `@lru_cache` avoids
unnecessary I/O and keeps the accessors pure and testable. A database
would be over-engineering at this scale.

### `specs` parsing at load time

The `products.csv` has a `specs` column containing JSON-as-string. It is
parsed once at load time into `specs_parsed` (a Python dict), so tools never
deal with string parsing.

### Token budget: Groq free tier constraints

The Groq free tier has strict limits (e.g. ~6,000 tokens per request on some
models, 8,000 tokens per minute, 1,000 requests per day). Every tool
**returns compact, JSON-serializable payloads** with only the fields the LLM
needs to answer:

- `search_products` returns `product_id`, `name`, `price_brl`,
  `final_price_brl`, `promotion`, `stock_quantity`, `status`, `category` —
  **not** long descriptions or specs.
- `limit` parameter (default 5, max 20) plus a `truncated` flag prevents the
  LLM from drowning in results.

This is deliberate: the tools do the heavy lifting (filtering, sorting,
applying promotions) and the LLM only orchestrates and writes the answer.

### Business rules encoded in tools

- **Promotions:** `final_price_brl` already includes active promotions.
  Only `is_active = 1` promotions are applied. PIX discount (5%) is **not**
  applied here — it is a payment-method discount, handled in prose by the LLM.
- **Status filtering:** `coming_soon` is always excluded (not on sale yet).
  `discontinued` is excluded by default and only included when
  `include_discontinued=True` is passed — useful when the agent needs to
  explain that a product left the catalog.
- **Stock:** `in_stock_only=True` by default, so customers don't get
  offered out-of-stock items.

### Order status: verification without leaking existence

`get_order_status` requires `order_id` **and** (`email` or `phone`) matching
the customer who placed the order. Two deliberate rules:

1. **Same error for "not found" and "wrong credentials".** Both return
   `{"ok": false, "error": "verification_failed"}`. Otherwise the tool could
   be used to probe whether a given `order_id` exists.
2. **Phone comparison is format-tolerant.** `(67) 98432-1098`,
   `67984321098`, and `+55 67 98432-1098` are all accepted, since the last
   10–11 digits are compared after stripping non-digits.

The payload returned on success is compact (status, tracking, items with
name/quantity/unit price, and a `next_step_hint` in PT-BR) — no customer
PII beyond the first name.

### Active promotions only — never offer an expired discount

`get_active_promotions` filters strictly on `is_active = 1` from
`promotions.csv`. The source file has 25 promotions but only **4** are
active at any given time (product IDs 127, 121, 90, 94 at the time of
writing). The store policy says *"nunca prometer um desconto que não está
mais vigente"*, and offering an expired campaign is the kind of mistake
that triggers customer complaints.

The tool also filters out promoted products that are `discontinued` or
`out of stock` — a discounted product that can't be sold is misleading.

Return payload includes a business-rule `note` reminding the LLM that
**promotions are not cumulative** and that the **PIX 5% discount does not
apply over promotional prices**. This lets the model enforce the policy in
prose without another tool call.

### Policy retrieval: TF-IDF over a cached, page-tagged index

The store policy lives in a single 8-page PDF. For a prototype, a full
embedding pipeline would be over-engineered. Instead:

- **Extraction:** `pypdf` extracts text page by page.
- **Cleaning:** pages with tables produce noisy private-use unicode
  characters. A targeted regex keeps printable ASCII, Latin-1 supplement,
  Latin Extended-A, and general punctuation — everything else is stripped.
  Unicode spaces (NBSP, narrow NBSP) are normalized to plain spaces.
- **Header stripping:** the running header *"Empório da Música Manual de
  Políticas e Procedimentos"* appears on every page and pollutes TF-IDF
  scores. It is stripped before fitting.
- **Chunking:** split on blank lines (paragraph level), merge adjacent
  paragraphs until ~600 characters. Keeps complete clauses together
  (e.g. sections 4.1–4.3 stay in one chunk).
- **Retrieval:** `TfidfVectorizer` with `ngram_range=(1, 2)`,
  `strip_accents="unicode"`, `sublinear_tf=True`. Unigrams match stems
  (`devolver` / `devolução`); bigrams preserve `direito de arrependimento`;
  accent stripping matters because users type without accents.
- **Threshold:** chunks scoring below `MIN_SCORE = 0.03` are dropped. If
  nothing passes, the tool returns `count=0` plus a note telling the LLM
  to say the manual doesn't cover the topic — better than returning
  garbage the LLM would paraphrase.
- **Page metadata:** each chunk carries its page number so the LLM can
  cite the source.
- **Caching:** the fitted vectorizer and matrix are cached with
  `@lru_cache(maxsize=1)`.

### System prompt language and structure

The `SYSTEM_PROMPT` is written in **Portuguese** on purpose: the target
customer writes in PT-BR, the source policy PDF is in PT-BR, and a
PT-BR prompt keeps the LLM in the correct tone and idiom. The README and
code comments are in English because the evaluation context
(Artefact's email: *"All responses must be in English!"*) is in English
— but the **agent's output language is the customer's language**.

The prompt is organized in fixed sections (persona, scope, tools, critical
rules, business rules, guardrails, examples). This makes it easy to audit
against the store's manual (sections 7.1, 7.2, 7.3) and easy to extend.
Example dialogues are included to anchor tone and demonstrate the
tool-calling flow — lightweight few-shot examples without burning tokens
on real demonstration calls.

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
  keeps `session.messages` JSON-serializable (useful for debugging and
  persistence).
- **Per-error handling.** `RateLimitError` → "try again in a few seconds".
  `APIStatusError 413` (request too large) → "start a new conversation".
  Generic `APIError` → neutral message. Each case is distinct because the
  user-facing advice differs.
- **Tool errors are results, not exceptions.** Invalid arguments from the
  LLM, unknown tool names, `TypeError` on the tool signature, or an
  unexpected exception inside a tool are all returned as
  `{"error": "...", "message": "..."}` in the `tool` message. The loop
  continues and the LLM gets a chance to fix its own call. This mirrors
  what production agents do: keep the conversation alive, let the model
  self-correct.
- **`temperature=0.3`, `max_tokens=800`, `reasoning_effort="none"`.**
  Consistency over creativity for customer service; Qwen's thinking mode
  disabled to save tokens.
- **`MAX_HISTORY_MESSAGES = 20` with a tool-aware trim.** When history
  grows past 20 messages, the oldest are dropped — but never in the middle
  of an `assistant.tool_calls → tool` sequence (which would break the API
  contract).

### Streamlit: chat UI with parallel display history

`app.py` keeps two parallel structures in `st.session_state`:

- **`agent_session`** — the `Session` from `src.agent`, holding the full
  internal history (`system`, `user`, `assistant` with `tool_calls`,
  `tool` results). This is what `run_turn` consumes and mutates.
- **`display_history`** — a lightweight list of
  `{role, content, tool_calls}` for rendering with `st.chat_message`.

Why two structures: the internal history includes JSON of tool results
(which would flood the UI) and a long system prompt (which should not be
shown to the customer). Keeping a separate display history makes the
render loop trivial and lets us optionally show tool calls in an expander
without affecting conversation state.

A sidebar toggle lets the operator see the tool calls that were made. It
is off by default to keep the customer-facing view clean, and useful in
demos to prove the agent is actually querying the data instead of
hallucinating.

### Tests: pytest over real CSVs, not mocks

`tests/test_tools.py` runs against the real CSVs and the real policy PDF,
not mocks. Rationale:

- The data is the **specification** of the challenge. A test that mocks
  `get_store()` would confirm that the mock returns what the mock was
  built to return — useless. Testing against the real CSVs catches the
  cases that actually matter: a promotion that stopped being active, a
  product that went out of stock, a phone format we forgot to handle.
- Fixtures are `scope="module"` so `get_store()` and `get_policy_index()`
  are loaded once per session (they are also `@lru_cache`d, so cost is
  negligible).

What is **not** tested, on purpose:

- **`src/agent.py` `run_turn`** — requires network calls and burns
  free-tier quota. `tests/manual_check_agent.py` is a smoke test run
  manually, not in CI.
- **Streamlit UI** — `app.py` is glue; testing it requires Streamlit's
  testing harness, which adds complexity for a prototype.

Coverage (by tool):

| Tool | What is tested |
|---|---|
| `search_products` | category filter, price range, name search, in-stock default, discontinued flag, promotion application, limit clamping, ordering |
| `get_order_status` | success via email, success via phone, phone format tolerance, `verification_required`, `verification_failed`, **same error** for nonexistent order, cancelled order notes, confirmed without tracking |
| `get_active_promotions` | only `is_active=1`, category filter, empty category, discount/final-price arithmetic |
| `search_policies` | empty query, real hits (payment, scope, warranty), `top_k` clamp, result shape |
| `DataStore` / `PolicyIndex` | row counts, `specs` parsing, chunk validity |

---

## Known limitations

- **Policy retrieval ranking is imperfect.** TF-IDF on a short Portuguese
  document with repeated domain vocabulary is prone to false positives:
  e.g. *"posso devolver um produto?"* can rank a section about
  discontinued products above the actual returns section, because
  "devolver"/"devolução" occurs in both. Empirically, the correct chunk
  appears in the **top 4** for every query tested in
  `tests/manual_check_tools.py`. The system prompt therefore instructs
  the LLM to read all returned chunks and select the one that actually
  answers the question, rather than automatically trusting chunk #1.

- **No date arithmetic on order status.** If a customer asks *"can I
  return order 1?"* and that order was delivered over a year ago, the
  agent confirms the 7-day window rule from the policy but does not
  calculate that the window has expired — it asks the customer for the
  delivery date instead. A production version should compare
  `estimated_delivery` against `today` and enforce the window
  automatically.

- **Order lookup is not real authentication.** Verification is
  `order_id` + (`email` or `phone`) matching the CSV, which is a
  reasonable prototype guard but not a security control. A real
  deployment would issue a one-time code to the email or phone on file.

- **Static data, no live inventory.** CSVs are read once at process
  start. An order confirmed by the human team is not reflected until
  the CSV is updated and the app restarted.

- **Groq free tier limits.** 30 RPM / 1,000 RPD / 8K TPM (Qwen 3.8 27B)
  constrain concurrency and history length. `MAX_HISTORY_MESSAGES = 20`
  mitigates the token side; a real deployment would need a paid tier or
  a self-hosted model.

- **`coming_soon` products are never offered.** A product with
  `status = "coming_soon"` (e.g. product 130, Kala KA-ABP-CTG) is
  hidden from all searches. Deliberate conservative choice — better to
  say "not yet available" than to take a pre-order the store cannot
  fulfill — but it means the agent cannot answer *"when will it
  arrive?"*.

- **`run_turn` is not covered by automated tests.** It requires network
  calls and burns free-tier quota. Manual smoke test only
  (`tests/manual_check_agent.py`). See below for how to fix this.

- **No multi-turn memory across sessions.** Each CLI run / Streamlit
  reload starts a fresh `Session`. Persistence would require an
  external store (SQLite, Redis).

---

## What I would do with more time

- **Replace TF-IDF with local embeddings.** `sentence-transformers`
  (`paraphrase-multilingual-MiniLM-L12-v2` or similar) would fix the
  ranking issues at the cost of ~120 MB of weights and a slower cold
  start. Combined with reranking, this is the single biggest quality
  win available.

- **Add date arithmetic in `get_order_status`.** Compare
  `estimated_delivery` against `datetime.today()` and return a
  `return_window_expires_at` field.

- **Deterministic tests for `run_turn`.** Inject a fake Groq client
  (already an optional parameter) that returns canned `tool_calls` and
  final messages. Test single-tool turn, multi-tool turn, invalid
  arguments, `MAX_TOOL_ITERATIONS` exhaustion, rate-limit recovery.

- **Response cache.** Memoize answers for the most common queries
  (hours, payment methods, scope) to reduce free-tier quota usage.

- **Human-in-the-loop handoff.** Add an explicit `escalate_to_human`
  tool that the LLM calls when confidence is low, with a payload the
  human team can pick up directly. Sections 7.3 and LGPD already imply
  this flow.

- **Structured evaluation.** A small test set of ~30 Q&A pairs with
  expected tool calls and expected facts, run in CI.

- **Docker + deployment.** `Dockerfile` with `uv` for reproducible
  builds; deploy Streamlit for a live demo link.

- **WhatsApp integration.** Twilio or Meta Cloud API webhook, since the
  store's real channel is WhatsApp (per the policy manual).

---

## Use of AI coding assistants

I used **Claude (Anthropic)** as the primary coding assistant throughout
this challenge, via chat. My workflow:

1. **Architecture first.** I defined the folder structure, data flow,
   and tool boundaries before writing code. The assistant proposed a
   structure; I adjusted it (e.g. chose `pyproject.toml` over
   `requirements.txt` after hitting a `ModuleNotFoundError` when running
   scripts from `tests/`).

2. **Tool-by-tool implementation with review.** Each tool was
   implemented and reviewed separately. I ran
   `tests/manual_check_tools.py` after each one and checked outputs
   against the real CSVs — several times the first draft returned the
   wrong rows or missed an edge case (out-of-stock, discontinued,
   phone-format tolerance) and I sent it back for correction.

3. **Prompt design in Portuguese.** The system prompt went through
   several iterations: the first version told the LLM to trust chunk #1
   of `search_policies`; after observing misroutes, I rewrote it to
   require reading all chunks.

4. **Debugging with the assistant.** Model-name errors (404 on
   `groq/qwen/qwen3.6-27b` → correct ID `qwen/qwen3.8-27b`), Groq
   free-tier limits, and `reasoning_effort="none"` were all diagnosed
   with the assistant's help.

5. **Manual review of every commit.** I read every diff before
   `git commit`. The assistant never committed on my behalf. Commits
   are incremental and reflect real progress, per the challenge
   requirement.

**What the assistant did not do:** it did not have access to my Groq key,
my GitHub account, or my CSVs beyond what I pasted. All test runs,
commits, and pushes were executed by me locally.

**What I would change:** for a production build I would pair the
assistant with a deterministic test suite from day one — the smoke
tests here were ad hoc and the lack of `run_turn` coverage is a direct
consequence.

---

## Example conversations

Five conversations covering the scenarios in the challenge brief are in
`examples/`:

| File | Scenario | Tools used |
|---|---|---|
| `01_product_search.md` | *"Quais violões disponíveis custando até R$ 1000?"* | `search_products` (category + price filter) |
| `02_price_lookup.md` | *"Quanto custa o Takamine GD20?"* | `search_products` (name query) |
| `03_return_policy.md` | *"Me arrependi da minha compra, posso devolver?"* | `search_policies` + `get_order_status` |
| `04_order_status.md` | *"Qual o status do meu pedido 1?"* | `get_order_status` (with verification) |
| `05_out_of_scope.md` | *"Vocês vendem cordas de violão?"* | `search_policies` (scope) |

Conversation 3 is the non-trivial one: it chains a policy lookup with an
order lookup, cites the manual's page, and offers human handoff.

---

## License

Internal challenge project — not for redistribution.