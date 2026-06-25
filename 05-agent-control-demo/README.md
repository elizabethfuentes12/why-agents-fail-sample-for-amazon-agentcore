[< Back to Main README](../README.md)

# AI Agent Guardrails That Self-Correct Instead of Block

[![Python](https://img.shields.io/badge/Python-3.12+-3776AB.svg?style=flat&logo=python&logoColor=white)](https://python.org)
[![Strands Agents](https://img.shields.io/badge/Strands_Agents-1.27+-00B4D8.svg?style=flat)](https://strandsagents.com)
[![Agent Control](https://img.shields.io/badge/Agent_Control-Steer_&_Deny-orange.svg?style=flat)](https://github.com/agentcontrol/agent-control)

> Hooks are functions that run at specific points in an agent's lifecycle. In this demo, hooks intercept tool calls and block them using `cancel_tool` when a business rule is violated. The agent reports failure and the user must retry. Agent Control goes further: it **steers** the agent to fix the problem and complete the task, instead of failing.

![Hooks (Block) vs Agent Control (Self-Correct) comparison](./images/hooks-vs-agent-control.png)

Based on: [Strands Agents with Agent Control](https://strandsagents.com/blog/strands-agents-with-agent-control/)

This demo uses Strands Agents and Agent Control. The guardrail patterns demonstrated (hooks, steering, symbolic rules) can be applied with other agent frameworks that support lifecycle hooks.

---

## The Problem with Blocking

[Demo 04 (Neurosymbolic Guardrails)](../04-neurosymbolic-demo/) demonstrates that hooks can enforce business rules at the tool level. When a rule is violated, `cancel_tool` blocks the call and the agent tells the user it cannot proceed.

But blocking alone has limitations. If a user requests 15 guests and the maximum is 10 per room, the agent could split the reservation into two rooms and complete the booking. Instead, with hooks alone, it asks the user to change their request, interrupting the flow.

## The Solution: Steer Instead of Block

![Agent Control steer flow: User Request → LLM → Agent Control server evaluates → Self-Correct → Final Response](./images/Agent-Control.png)

[Agent Control](https://github.com/agentcontrol/agent-control) introduces **steer controls** — policies (defined in local YAML or managed on a server) that guide the agent to self-correct when a violation is detected, instead of terminating the operation:

| Approach | 15 guests requested | Result |
|----------|-------------------|--------|
| **Hooks** | BLOCKED | "Would you like to adjust?" (flow stopped) |
| **Agent Control** | Guide("split into two rooms") | Books 10 + 5, BK002 and BK003 confirmed (flow completed) |

## How It Differs from Hooks

| | Hooks ([Demo 04](../04-neurosymbolic-demo/)) | Agent Control (this demo) |
|---|---|---|
| Where rules live | Python code (`rules.py`) | Server or local `controls.yaml` |
| When a rule fails | `cancel_tool = "BLOCKED"` → agent fails | `Guide("split into two rooms")` → agent retries corrected |
| To change a rule | Edit code, redeploy | Edit YAML or call the API — no agent code changes |
| Integration | `HookProvider` + `hooks=[...]` | `Plugin` + `plugins=[...]` |
| Evaluators | Custom Python lambdas | Built-in: regex (pattern matching), list (exact value matching), JSON (structure validation), SQL. Plus optional external evaluators such as Galileo Luna-2 for semantic evaluation (installed separately) |
| Scope | `BeforeToolCallEvent` only | LLM input/output, tool input/output, pre/post |

## The Tools

Three booking tools in `tools.py` — clean, no validation logic:

| Tool | What it does | Key behavior |
|------|-------------|--------------|
| `book_hotel(hotel, check_in, check_out, guests)` | Books a hotel room | Returns `"SUCCESS: Booking BK001..."` — no guest limit in the tool |
| `process_payment(amount, booking_id)` | Processes payment | Returns `"SUCCESS"` or `"ERROR: Booking not found"` |
| `confirm_booking(booking_id)` | Confirms a booking | Returns `"SUCCESS: Confirmed BK001"` |

The tools do NOT enforce the max-guests rule. That is the guardrail layer's job — either Hooks or Agent Control.

Agent Control integrates as a Plugin with two lines:

```python
# Hooks (existing approach — block):
agent = Agent(tools=[...], hooks=[MaxGuestsHook()])

# Agent Control (new approach — steer):
agent = Agent(tools=[...], plugins=[AgentControlPlugin(...), AgentControlSteeringHandler(...)])
```

## What We Test

Same query, same tools, same model — only the guardrail changes:

| Test | Guardrail | Outcome |
|------|-----------|---------|
| 1 — Hooks | `MaxGuestsHook` with `cancel_tool` | Agent is BLOCKED → asks user what to do |
| 2 — Agent Control | `AgentControlSteeringHandler` with `Guide()` | Agent self-corrects → splits into two rooms (10 + 5), booking completes |

---

## Two Ways to Define Controls

| Mode | Best for | How it works |
|------|----------|-------------|
| **Local YAML** (this demo) | Quick prototyping, single-developer projects, running with no extra infrastructure | Controls defined in `controls.yaml` — no server needed. `agent_control.init(controls_file="controls.yaml")` |
| **Server** | Teams, production, dashboard management | Controls live on the Agent Control server — change via API or dashboard without redeploying |

This demo runs **local-first**: it tries to reach an Agent Control server, and if none is available it loads the controls from `controls.yaml`. You can run the whole demo with no server. See the [Agent Control docs](https://docs.agentcontrol.dev/) for server setup if you want centralized, dashboard-managed controls.

---

## Prerequisites

- **Python 3.12+** — required by `agent-control-sdk` (earlier versions only ship an empty placeholder package on Python 3.11 and below)
- OpenAI API key — get one at https://platform.openai.com/api-keys (or use any [supported model provider](https://strandsagents.com/docs/user-guide/concepts/model-providers/) such as Amazon Bedrock or Anthropic)
- Agent Control server — **optional**. The demo runs local-first from `controls.yaml`; a server is only needed for centralized, dashboard-managed controls (see [setup instructions](https://github.com/agentcontrol/agent-control))

---

## Quick Start

### 1. Install dependencies

```bash
uv venv --python 3.12 && uv pip install -r requirements.txt
```

### 2. Configure API key

Create a `.env` file with your real OpenAI key (replace `sk-...` with the key from https://platform.openai.com/api-keys):

```bash
echo "OPENAI_API_KEY=sk-..." > .env
```

### 3. Run the comparison

```bash
uv run test_hooks_vs_control.py
```

Or open `test_hooks_vs_control.ipynb` in your IDE (VS Code, Kiro, or any editor with notebook support).

The controls are loaded automatically from `controls.yaml` — no server required.

### Optional: use an Agent Control server

To manage controls centrally instead of from the local YAML file, start the [Agent Control server](https://github.com/agentcontrol/agent-control), register the controls, then re-run the demo:

```bash
# Verify the server is running (default port 8000)
curl 127.0.0.1:8000/health

# Register the controls on the server
uv run setup_controls.py
```

---

## Controls

The demo runs a single **steer** control, defined in `controls.yaml`:

| Control | Type | Scope | What it does |
|---------|------|-------|-------------|
| `steer-max-guests` | STEER | LLM output (post) | When the agent's text mentions more than 10 guests, guides it to split the booking into rooms of 10 + 5 and report both booking IDs |

`setup_controls.py` also registers a second **deny** control (`deny-no-payment`) to illustrate the hard-block pattern on a server. It is scoped to `confirm_booking` and blocks confirmation when the input matches a booking ID — use it when you want to demonstrate deny-style enforcement, not the self-correcting steer flow shown here.

---

## Expected Output

```
Test 1 — Hooks:          "Would you like to adjust the number of guests?"           (blocked)
Test 2 — Agent Control:  "Split into two rooms: BK002 (10 guests) + BK003 (5)."     (self-corrected)
```

---

## Cleanup

Stop the Agent Control server following the [shutdown instructions](https://docs.agentcontrol.dev/).

---

## Files

| File | Purpose |
|------|---------|
| `tools.py` | Booking tools — clean, no validation logic |
| `controls.yaml` | Steer control loaded local-first when no server is running |
| `setup_controls.py` | Registers steer + deny controls on an Agent Control server (optional) |
| `test_hooks_vs_control.py` | Runs both approaches on the same query, compares results |
| `test_hooks_vs_control.ipynb` | Interactive notebook version |
| `requirements.txt` | Dependencies |

---

## References

### Research
- [ATA: Autonomous Trustworthy Agents (2024)](https://arxiv.org/html/2510.16381v1) — Guardrail failure patterns in AI agents
- [Enhancing LLMs through Neuro-Symbolic Integration](https://arxiv.org/pdf/2504.07640v1) — Combining neural + symbolic reasoning

### Strands Agents
- [Strands Agents with Agent Control](https://strandsagents.com/blog/strands-agents-with-agent-control/) — Blog announcement
- [Agent Control Plugin](https://strandsagents.com/docs/community/plugins/agent-control/) — Strands integration docs
- [Strands Hooks](https://strandsagents.com/docs/user-guide/concepts/agents/hooks/) — `BeforeToolCallEvent`, `cancel_tool`
- [Strands Steering](https://strandsagents.com/docs/user-guide/concepts/plugins/steering/) — `Guide`, `Proceed`, `SteeringHandler`
- [Strands Model Providers](https://strandsagents.com/docs/user-guide/concepts/model-providers/amazon-bedrock/) — Swap to Amazon Bedrock, Anthropic, Ollama

### Agent Control
- [Agent Control GitHub](https://github.com/agentcontrol/agent-control) — Open source, Apache 2.0
- [Agent Control Docs](https://docs.agentcontrol.dev/) — Server setup and API reference

---

## Frequently Asked Questions

### What is the difference between Agent Control and Amazon Bedrock AgentCore?

They are different products. **Agent Control** is an open-source guardrail server that evaluates agent actions and returns steer/deny decisions — it runs locally or on any infrastructure. **Amazon Bedrock AgentCore** is an AWS managed service for hosting and deploying agents in production with MCP routing, observability, and scaling. Demo 05 uses Agent Control for steering; [Demo 06](../06-agentcore-production-demo/) uses Amazon Bedrock AgentCore for production deployment.

### When should I use steering (Agent Control) instead of blocking (hooks)?

Use **hooks** (blocking) when the violation is a hard constraint that cannot be self-corrected — for example, confirming a booking without payment. Use **steering** (Agent Control) when the agent can adjust and complete the task — for example, splitting 15 guests into two rooms of 10 + 5 and informing the user. Steering reduces user friction because the task completes instead of failing.

### Can I use the steering pattern with other agent frameworks?

Yes. The steer-instead-of-block pattern is framework-agnostic. Agent Control integrates as a plugin with Strands Agents, but the concept — intercepting LLM output, evaluating it against rules, and injecting corrective guidance — can be implemented in any agent framework that supports middleware or output hooks.

---

## Navigation

- **Previous:** [Demo 04 - Neurosymbolic Guardrails](../04-neurosymbolic-demo/)
- **Next:** [Demo 06 - Amazon Bedrock AgentCore Production](../06-agentcore-production-demo/) — Deploy all techniques to production on AWS

---

## Security

If you discover a potential security issue in this project, notify AWS/Amazon Security via the [vulnerability reporting page](https://aws.amazon.com/security/vulnerability-reporting/?trk=87c4c426-cddf-4799-a299-273337552ad8&sc_channel=el). Please do **not** create a public GitHub issue.

---

## License

This library is licensed under the MIT-0 License. See the [LICENSE](../LICENSE) file for details.
