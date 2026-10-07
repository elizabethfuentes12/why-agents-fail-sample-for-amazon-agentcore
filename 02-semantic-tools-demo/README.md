[< Back to Main README](../README.md)

# Semantic Tool Selection: Fewer Tokens, Fewer Wrong Picks

[![Python](https://img.shields.io/badge/Python-3.9+-3776AB.svg?style=flat&logo=python&logoColor=white)](https://python.org)
[![Strands Agents](https://img.shields.io/badge/Strands_Agents-1.58-00B4D8.svg?style=flat)](https://strandsagents.com)
[![FAISS](https://img.shields.io/badge/FAISS-Semantic_Filtering-blue.svg?style=flat)](https://github.com/facebookresearch/faiss)

> A small model with a big, overlapping toolbox gets confused: it picks the wrong tool, or none, and pays for every tool description on every call. This demo gives the agent a ~40-tool travel pool and a Strands hook that trims it to the FAISS top-3 most relevant tools per request — cutting tokens sharply and reducing the chance of a wrong pick.

![Two bands over the same large tool pool. Sending every tool on each query costs the full set of descriptions and lets similar names such as search_hotels_by_city and search_hotels_by_rating compete. Filtering to the top 3 with FAISS over tool name and docstring sends only the relevant descriptions and narrows the choice](images/semantic-tool-selection-filtering.png)

## The Problem

Tool-calling hallucinations fall into several types, following the taxonomy in ["Internal Representations as Indicators of Hallucinations in Agent Tool Selection"](https://arxiv.org/abs/2601.05214): calling non-existent tools, choosing semantically wrong tools, malformed arguments, missing parameters, and skipping the tool entirely.

Two problems get worse as the toolbox grows:

- **Token waste** — every tool description is sent on *every* request, whatever the question asks for.
- **Wrong picks** — many near-duplicate tools (`search_*`, `get_*`, `check_*` variants) compete, and a small model picks the wrong one.

This demo uses a deliberately large, overlapping pool and a small model (**Claude Haiku**) so both effects are visible.

## The Solution: A Semantic-Selection Hook

![Two phases. At startup the hook embeds the name and docstring of every tool with Amazon Bedrock Nova 2 into a FAISS index. Per query it embeds the question with the same model, ranks all tools by cosine distance, keeps the closest three, and replaces the agent's live tool_registry with those 3](images/semantic-tool-selection.png)

`SemanticToolHook` is a Strands `HookProvider`, **not** Python wrapped around the agent. The agent is created with **all** the tools; on every request (`BeforeInvocationEvent`) the hook:

1. reads the user's latest message,
2. embeds it with Amazon Bedrock Nova 2 and finds the top-3 tools by FAISS cosine distance over each tool's **name + docstring**, and
3. replaces the agent's live `tool_registry` with just those 3.

Because the agent owns the registry and the hook mutates it per request, this is a production-shaped pattern: one long-lived agent, tools trimmed per turn, conversation memory intact.

```python
from strands import Agent
from strands.models import BedrockModel
from semantic_tools import ALL_TOOLS, SemanticToolHook

hook = SemanticToolHook(ALL_TOOLS, top_k=3)
agent = Agent(model=MODEL, tools=ALL_TOOLS, hooks=[hook],
              system_prompt="Use the single best tool to answer.")
agent("How much does a room cost at Cliffside Resort?")
# the hook trims 40 tools -> 3 before the model sees them
```

## Honest Framing: What the Numbers Mean

- **Token saving is the solid headline (~73%).** Sending 3 tool descriptions instead of ~40 cuts input tokens on every call, and the saving compounds across a conversation. The notebook prints the exact figure from `result.metrics.accumulated_usage` for your own run.
- **Accuracy is equal-or-better, shown as observed.** A strong small model is non-deterministic, so the notebook measures accuracy both ways (all 40 tools vs top-3) rather than asserting a fixed improvement. Fewer, relevant tools generally help.
- **The trade-off is real.** Top-k filtering can only help if the right tool is in the top-k. If FAISS misranks the correct tool out of the top-3, the agent can't call it at all. Tune `top_k` and write clear, distinct docstrings; the notebook calls this out.

## The Tools Are Real (not dumb mocks)

The pool mixes genuinely-working tools with realistic stand-ins:

- **Hotels** — read-only Neo4j (`search_hotels_by_city`, `get_hotel_room_rates`, `get_hotel_amenities`) over the demo-01 graph.
- **Weather** — the free [Open-Meteo](https://open-meteo.com) API (no key, no signup): `get_current_weather`, `get_weather_forecast`.
- **Bookings** — a JSON booking store (`book_hotel`, `get_booking`), swappable to Amazon DynamoDB without changing agent code.
- **~33 realistic stand-ins** — flights, car rentals, currency, visas, etc. that return plausible data. The demo is about tool *selection*, so these return canned results; their overlap with the real tools is what makes selection hard.

## Memory Across Sessions

The last part of the notebook (and `chat.py`) adds a **session manager**: `SnapshotSessionManager` + `LocalFileStorage` persists the conversation to `./sessions/`, so an agent created later with the same `session_id` resumes where it left off — the same semantic hook keeps trimming tools per turn.

## Quick Start

### Prerequisites

- Python 3.9+
- An AWS account with [Amazon Bedrock](https://aws.amazon.com/bedrock/) access (Claude Haiku + Nova 2 embeddings). **No external API key is needed.**
- A running Neo4j with the hotel graph (built in [Demo 01](../01-graphrag-demo/); inside Workshop Studio it is restored from a dump). The three Neo4j hotel tools need it; the rest of the pool runs without it.

### Install

```bash
cd 02-semantic-tools-demo
uv venv && uv pip install -r requirements.txt
cp ../01-graphrag-demo/.env .env   # or set NEO4J_* yourself
```

That is everything the FAISS demo (`chat.py` and the notebook) needs.

### Optional: run the decision-model versions

The decision-model files (`chat_decider.py`, `model_routing_with_jev.py`, and
Part 5 of the notebook) need one or two extra installs. Do only the one you want.

**Strands Decider (local 2B model), for `chat_decider.py`:**

```bash
uv pip install strands-decider
```

The first run downloads the ~2B model weights from Hugging Face (a few GB) and
caches them, so the first launch is slow and later ones are fast. No API key, no
account; it runs on your CPU. Then:

```bash
AWS_PROFILE=<profile> AWS_REGION=us-east-1 python chat_decider.py
```

**Jev (hosted decision model), for `model_routing_with_jev.py`:**

```bash
uv pip install "strands-decider[jev]"      # installs the TypeSafe SDK
```

Get an API key at [openrouter.ai/keys](https://openrouter.ai/keys), add a little
credit (Jev is cheap), then set it in your shell:

```bash
export OPENROUTER_API_KEY=sk-or-...
AWS_PROFILE=<profile> AWS_REGION=us-east-1 python model_routing_with_jev.py
```

### Run

```bash
# Notebook (recommended) — open in VS Code, Kiro, or Jupyter
token_efficiency_analysis.ipynb

# Or the interactive REPL (persistent memory across restarts)
AWS_PROFILE=<profile> AWS_REGION=us-east-1 python chat.py

# Same demo, but a decision model picks the tool instead of FAISS
# (needs: uv pip install strands-decider — see "Optional" above)
AWS_PROFILE=<profile> AWS_REGION=us-east-1 python chat_decider.py
```

## Files

| File | What it is |
|------|------------|
| `token_efficiency_analysis.ipynb` | The walkthrough: the big pool + small model (Part 1), the `SemanticToolHook` harness (Part 2), accuracy & tokens all-40 vs top-3 (Part 3), session memory (Part 4), and picking the tool with a decision model instead of FAISS (Part 5). |
| `semantic_tools.py` | `ALL_TOOLS` (the ~40-tool pool: real hotel/weather/booking + stand-ins) and `SemanticToolHook`, copied so `chat.py` can import them. |
| `booking_store.py` | JSON booking store (`book_hotel`, `get_booking`), swappable to DynamoDB. |
| `chat.py` | REPL using the FAISS hook + `SnapshotSessionManager` for persistent memory. |
| `chat_decider.py` | Same REPL, but a decision model (`strands-decider` 2B, local) picks the tool instead of FAISS. |
| `model_routing_with_jev.py` | Separate example: Strands model routing where a decision model (Jev, hosted) chooses which model serves each request. |

## How It Works

### Baseline — all tools, every query

```python
# Agent sees ALL ~40 tools on every query
agent = Agent(model=MODEL, tools=ALL_TOOLS)
agent("How much does a room cost at Cliffside Resort?")
# Cost: all ~40 tool descriptions, every query. Risk: wrong pick among 40.
```

### Semantic — the hook trims to top-3

```python
hook = SemanticToolHook(ALL_TOOLS, top_k=3)
agent = Agent(model=MODEL, tools=ALL_TOOLS, hooks=[hook])
agent("How much does a room cost at Cliffside Resort?")
# The hook replaces the registry with the 3 closest tools before the model runs.
# Cost: 3 descriptions. Risk: wrong pick among 3 — if the right tool was in the top-3.
```

### Decision model — the model picks the tool

```python
hook = DeciderToolHook(ALL_TOOLS)   # strands-decider 2B, local
agent = Agent(model=MODEL, tools=ALL_TOOLS, hooks=[hook])
agent("How much does a room cost at Cliffside Resort?")
# Same before-invocation hook, but a decision model returns a calibrated pick
# over the tool names — no embeddings, no index, no generated text.
```

FAISS and the decision model are independent and interchangeable inside the same
hook. FAISS ranks by embedding distance (needs an index, costs embedding tokens);
the decision model returns a calibrated choice (no index, no embeddings). See
`chat_decider.py` and Part 5 of the notebook.

## Further Reading

- [Introducing Strands Decider](https://strandsagents.com/blog/introducing-strands-decider/) — the open-source Strands decision model (2B) used in `chat_decider.py` and Part 5.

- [Internal Representations as Indicators of Hallucinations in Agent Tool Selection](https://arxiv.org/abs/2601.05214) — source of the tool-calling hallucination taxonomy. It detects hallucinations from a model's internal representations; it does not evaluate embedding pre-filtering, so none of this demo's numbers come from it.
- [Search for tools in your Amazon Bedrock AgentCore Gateway with a natural-language query](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-using-mcp-semantic-search.html) — the same idea as a managed service for production MCP tool routing.

## Frequently Asked Questions

### How much does semantic tool selection reduce token usage?

A lot — the demo measures it rather than asserting a figure. Instead of sending ~40 tool descriptions on every query, the hook sends the top 3. In the notebook's run that is roughly a 73% reduction, and it repeats on every turn. The exact number depends on how many tools you have and how long their docstrings are; the notebook prints the figure for your own run.

### Does filtering tools break conversation memory?

No. The hook mutates the agent's `tool_registry` in place on a long-lived agent; `agent.messages` is untouched. For persistence across restarts, `chat.py` adds `SnapshotSessionManager`.

### Can I use this with other agent frameworks?

Yes. The core pattern — embed tool descriptions, index with FAISS, filter by cosine similarity before the LLM sees them — is framework-agnostic. This demo expresses it as a Strands hook. Amazon Bedrock AgentCore Gateway also offers built-in [MCP semantic routing](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-using-mcp-semantic-search.html) for production workloads.

---

## Navigation

- **Previous:** [Demo 01 - Graph-RAG vs RAG](../01-graphrag-demo/)
- **Next:** [Demo 03 - Multi-Agent Validation](../03-multiagent-demo/): catch confident guesses on subjective questions with a heterogeneous model consortium.

---

## Security

If you discover a potential security issue in this project, notify AWS/Amazon Security via the [vulnerability reporting page](https://aws.amazon.com/security/vulnerability-reporting/). Please do **not** create a public GitHub issue.

---

## License

This library is licensed under the MIT-0 License. See the [LICENSE](../LICENSE) file for details.
