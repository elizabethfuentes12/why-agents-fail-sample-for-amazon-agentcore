# LangGraph Demos - Reducing AI Agent Hallucinations

LangGraph versions of demos 01-05, ported from [Strands Agents](https://strandsagents.com). Similar patterns can be applied in AutoGen, CrewAI, or other agent frameworks.

> **Prerequisite**: Familiarity with Python and basic LLM concepts. Each demo builds on the previous one.

## Demos

| Demo | Technique | Strands Pattern | LangGraph Equivalent |
|------|-----------|-----------------|---------------------|
| [01-faq-graphrag](./01-faq-graphrag-langgraph/) | RAG vs Graph-RAG | Two separate `Agent()` instances | Two independent `StateGraph` with tool-calling loops |
| [02-semantic-tools](./02-semantic-tools-langgraph/) | Semantic tool filtering (29→3 tools) | `swap_tools()` on live agent | Preprocessing node + dynamic `bind_tools()` |
| [03-multiagent](./03-multiagent-langgraph/) | Multi-agent validation (Executor→Validator→Critic) | `Swarm` with `handoff_to_agent()` | Sequential `StateGraph` with conditional retry |
| [04-neurosymbolic](./04-neurosymbolic-langgraph/) | Neurosymbolic guardrails | `HookProvider` + `BeforeToolCallEvent` | Guardrail node between LLM and tool execution |
| [05-agent-control](./05-agent-control-langgraph/) | Block vs Steer (DENY/STEER) | `AgentControlPlugin` + `SteeringHandler` | Steering node evaluates LLM output + guidance retry |

## Quick Start

```bash
cd <demo-folder>
uv venv && uv pip install -r requirements.txt
cp .env.example .env  # add your OPENAI_API_KEY
uv run python <script>.py
```

## LangGraph Core Concepts

### 1. StateGraph and State

```python
from langgraph.graph import StateGraph, MessagesState, START, END

# MessagesState = TypedDict with messages: list (accumulated via reducer)
graph = StateGraph(MessagesState)
```

The state flows through every node. Each node receives the current state and returns updates.

### 2. Nodes and Edges

```python
graph.add_node("llm", llm_function)       # A node is a function
graph.add_node("tools", tool_function)

graph.add_edge(START, "llm")               # Fixed edge
graph.add_edge("tools", "llm")             # After tools, back to LLM
graph.add_conditional_edges("llm", router)  # Dynamic routing
```

### 3. The Basic Agentic Loop

```
START -> llm_node --[has tool_calls?]--> tool_node -> llm_node
                  \--[no tool_calls]---> END
```

This is the foundation of every demo. Demo 02 adds a filter node before the LLM, Demo 03 chains multiple agents, Demo 04 adds a guardrail node between LLM and tools, and Demo 05 adds a steering node that evaluates LLM output for self-correction.

### 4. Key Differences from Strands

| Concept | Strands | LangGraph |
|---------|---------|-----------|
| Tool decorator | `from strands import tool` | `from langchain_core.tools import tool` |
| Agent creation | `Agent(tools=, model=, hooks=)` | `StateGraph` + nodes + edges + `compile()` |
| Tool binding | Implicit (passed to Agent) | Explicit: `model.bind_tools(tools)` |
| Hooks/Guards | `HookProvider` subclass | Graph node between LLM and tools |
| Multi-agent | `Swarm([agents], entry_point=)` | Sequential nodes with conditional edges |
| State | Implicit in agent context | Explicit `TypedDict` with reducers |
| Invocation | `agent("query")` | `graph.invoke({"messages": [HumanMessage(...)]})` |

## Architecture Diagrams

### Demo 01: Basic Tool Agent
```
START -> llm_node -> [tool_calls?] -> tool_node -> llm_node -> END
```

### Demo 02: Semantic Tool Filtering
```
START -> filter_tools -> llm_node -> [tool_calls?] -> tool_node -> llm_node -> END
```

### Demo 03: Multi-Agent Validation
```
START -> executor -> validator -> critic -> [approved?] -> END
                                    |                       ^
                                    \--[rejected]-> executor-+  (retry)
```

### Demo 04: Neurosymbolic Guardrails
```
START -> llm_node -> [tool_calls?] -> guardrail -> [blocked?] -> llm_node (steering)
                  |                             \-> tool_node -> llm_node
                  \--[no tools]--> END
```

### Demo 05: Block vs Steer (Agent Control)
```
START -> llm_node -> steer_check -> [steered?] -> llm_node (retry with guidance)
                                 \-> guardrail -> [denied?] -> llm_node (hard block)
                                               \-> tool_node -> llm_node -> END
```

### Progression to Production (Demo 06)

```
Demo 04 (Block)     -> Demo 05 (Steer)      -> Demo 06 (Production)
rules.py            -> controls.py           -> DynamoDB items
Guardrail node      -> Steer + guardrail     -> Lambda + steering
Task FAILS          -> Task COMPLETES        -> Task COMPLETES
Edit code, restart  -> Edit controls.py      -> Update DynamoDB (instant)
```

---

## Contributing

Contributions are welcome! See [CONTRIBUTING](../CONTRIBUTING.md) for more information.

---

## Security

If you discover a potential security issue in this project, notify AWS/Amazon Security via the [vulnerability reporting page](http://aws.amazon.com/security/vulnerability-reporting/). Please do **not** create a public GitHub issue.

---

## License

This library is licensed under the MIT-0 License. See the [LICENSE](../LICENSE) file for details.
