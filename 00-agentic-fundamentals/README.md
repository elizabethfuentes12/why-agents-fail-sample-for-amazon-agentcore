# 00 · Agentic Fundamentals

Start here if you are new to AI agents or to [Strands Agents](https://strandsagents.com). These two short modules cover the building blocks every demo in this repo uses: **the agent loop, tools, and hooks**.

| # | Module | What you learn | Run |
|:-:|--------|----------------|-----|
| 01 | [Agent Loop + Tools](./01-agent-loop-tools/) | An agent is a model plus tools in a loop: `User → LLM → Tool Call → Tool Result → LLM → Response`. A tool is a Python function with `@tool`, and the model reads its docstring to decide when to call it. | `module-01-agent-loop-tools.ipynb` or `python chat.py` |
| 02 | [Hooks](./02-hooks/) | Hooks run your own deterministic code at fixed points of the agent loop. Here a `RateLimiterHook` on `BeforeToolCallEvent` caps how many times each tool can be called per request. | `module-02-hooks.ipynb` or `python chat.py` |

Both modules use the same customer-service agent (`lookup_customer`, `get_order_history`, `process_refund`, mock data in `customer_service_tools.py`), so the only thing that changes from 01 to 02 is the hook.

## Why these two first

The why-agents-fail demos build on these ideas:

- **Tools:** Demo 02 (semantic tool selection) is about which tools the model is offered and which one it picks. It only makes sense once you know that the model chooses a tool from its name and docstring.
- **Hooks:** Demo 02 swaps the tools per request with a hook, and Demo 04 enforces symbolic rules with hooks. Demo 05 compares a hook that blocks a tool call with native Strands steering, which guides the agent to fix the call instead.

## Prerequisites

- Python 3.10+
- AWS credentials with Amazon Bedrock access (Strands Agents uses Amazon Bedrock by default). To use another provider, see the comments in each `chat.py` or the [model providers](https://strandsagents.com/docs/user-guide/sdk/model-providers/) docs.

```bash
cd 00-agentic-fundamentals/01-agent-loop-tools   # or 02-hooks
uv venv && uv pip install -r requirements.txt
# open the notebook in your IDE (Kiro, VS Code, JupyterLab), or:
uv run chat.py
```

## Source

Modules 01 and 02 of the [Strands Agents hands-on workshop](https://github.com/aws-samples/sample-strands-agents-hands-on-workshop) (`samples/01-agent-loop-tools` and `samples/02-hooks`). Only the paths and the "what's next" links were changed so they point to this repo. The rest of that workshop (skills and steering, session managers, deploy, multi-agent, evals) goes deeper into Strands Agents.

## Next

**[Demo 01: Graph-RAG vs RAG](../01-faq-graphrag-demo/)**: the first way agents fail, with fabricated statistics, incomplete retrieval and out-of-domain answers.
