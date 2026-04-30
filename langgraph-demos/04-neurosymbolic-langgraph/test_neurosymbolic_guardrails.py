"""
Demo 04 - Neurosymbolic Guardrails with LangGraph
===================================================

KEY CONCEPT: Enforce business rules that the LLM CANNOT bypass.
Rules are executable code (verifiable), not prompt text (bypassable).

LANGGRAPH ARCHITECTURE:
    The key innovation: a GUARDRAIL NODE sits between the LLM and tool execution.
    It intercepts tool calls and validates them against symbolic rules.

    START -> llm_node --[tool_calls?]--> guardrail -> (blocked?) -> llm_node (with error)
                      |                            +-> tool_node -> llm_node
                      \--[no tools]---> END

    DIAGRAM:
        START -> llm_node -> guardrail --[all allowed]--> tool_node -> llm_node
                    ^            |
                    |            \--[some blocked]------> llm_node (steering)
                    |
                    \--[no tools]--> END

WHAT YOU'LL LEARN:
    1. How to implement guardrails as graph nodes (not hooks)
    2. How to intercept and block tool calls before execution
    3. How to send "steering messages" back to the LLM when a rule is violated
    4. The difference between Strands Hooks and LangGraph guardrail nodes

KEY DIFFERENCE FROM STRANDS:
    Strands Hooks:
      - Subclass HookProvider, implement register_hooks()
      - Set event.cancel_tool to block a tool call
      - Framework handles the interception automatically

    LangGraph Guardrail Node:
      - A regular graph node that sits between LLM and tools
      - Reads tool_calls from the AIMessage
      - Returns ToolMessages with BLOCKED content for violations
      - The LLM sees the blocking message and adjusts its behavior
      - More explicit, more visible in the graph structure
"""
import os

os.environ["OTEL_SDK_DISABLED"] = "true"

from dotenv import load_dotenv

load_dotenv()

from langgraph.graph import StateGraph, MessagesState, START, END
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage

from typing import Literal
from datetime import datetime

from rules import (
    BOOKING_RULES,
    CONFIRMATION_RULES,
    CANCELLATION_RULES,
    validate,
)

# ---------------------------------------------------------------------------
# APPLICATION STATE (shared mutable state, external to the graph)
# ---------------------------------------------------------------------------
STATE = {
    "bookings": {
        "BK001": {"hotel": "Grand Hotel", "check_in": "2026-02-15", "guests": 2}
    },
    "payments": {},
}

# ---------------------------------------------------------------------------
# TOOL DEFINITIONS (clean, no validation logic)
# ---------------------------------------------------------------------------
# Notice: these tools have ZERO validation code inside them.
# All business rules are enforced by the guardrail node.
# This is the "separation of concerns" principle:
#   - Tools do their job (book, cancel, pay, confirm)
#   - Guardrails enforce the rules (dates, guests, payments)


@tool
def book_hotel(hotel: str, check_in: str, check_out: str, guests: int = 1) -> str:
    """Book a hotel room for specified dates and number of guests."""
    return f"SUCCESS: Booked {hotel} for {guests} guests, {check_in} to {check_out}"


@tool
def cancel_booking(booking_id: str) -> str:
    """Cancel an existing hotel booking."""
    return f"SUCCESS: Cancelled booking {booking_id}"


@tool
def process_payment(amount: float, booking_id: str) -> str:
    """Process payment for a booking."""
    if booking_id not in STATE["bookings"]:
        return "ERROR: Booking not found"
    STATE["payments"][booking_id] = amount
    return f"SUCCESS: Processed ${amount} for {booking_id}"


@tool
def confirm_booking(booking_id: str) -> str:
    """Confirm a booking after payment has been processed."""
    return f"SUCCESS: Confirmed {booking_id}"


ALL_TOOLS = [book_hotel, cancel_booking, process_payment, confirm_booking]

# ---------------------------------------------------------------------------
# MODEL
# ---------------------------------------------------------------------------
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
model_with_tools = llm.bind_tools(ALL_TOOLS)
tools_by_name = {t.name: t for t in ALL_TOOLS}

# ---------------------------------------------------------------------------
# RULE-TO-TOOL MAPPING
# ---------------------------------------------------------------------------
# Maps each tool name to its set of business rules.
# This is the same mapping that was in NeurosymbolicHook.__init__() in Strands.
TOOL_RULES = {
    "book_hotel": BOOKING_RULES,
    "confirm_booking": CONFIRMATION_RULES,
    "cancel_booking": CANCELLATION_RULES,
}


def build_context(tool_name: str, params: dict) -> dict:
    """Build validation context from tool parameters.

    This is equivalent to NeurosymbolicHook._build_context() in Strands.
    Transforms raw tool parameters into the format expected by rules.
    """
    if tool_name == "book_hotel":
        try:
            ci = datetime.strptime(params["check_in"], "%Y-%m-%d")
            co = datetime.strptime(params["check_out"], "%Y-%m-%d")
            return {
                "check_in": ci,
                "check_out": co,
                "guests": params.get("guests", 1),
                "days_until_checkin": (ci - datetime.now()).days,
            }
        except (ValueError, KeyError):
            # Return context that fails validation
            return {
                "check_in": None,
                "check_out": None,
                "guests": 999,
                "days_until_checkin": -999,
            }
    elif tool_name == "confirm_booking":
        return {
            "payment_verified": params.get("booking_id", "") in STATE["payments"]
        }
    elif tool_name == "cancel_booking":
        booking = STATE["bookings"].get(params.get("booking_id", ""))
        if booking:
            ci = datetime.strptime(booking["check_in"], "%Y-%m-%d")
            return {
                "booking_id": params.get("booking_id"),
                "days_until_checkin": (ci - datetime.now()).days,
            }
        return {"booking_id": None}
    return {}


# ---------------------------------------------------------------------------
# GRAPH NODES
# ---------------------------------------------------------------------------


def llm_node(state: MessagesState):
    """LLM node - calls the model with all tool definitions."""
    messages = [
        SystemMessage(
            content="You are a hotel booking assistant. Use the available tools to help users."
        )
    ] + state["messages"]
    response = model_with_tools.invoke(messages)
    return {"messages": [response]}


def guardrail_node(state: MessagesState):
    """
    GUARDRAIL NODE - The core of neurosymbolic validation in LangGraph.

    This node intercepts ALL tool calls and validates them against
    symbolic business rules BEFORE they are executed.

    HOW IT WORKS:
    1. Read tool_calls from the last AIMessage
    2. For each tool call, check if it has associated rules
    3. Build context from tool parameters
    4. Run validate() against the rules
    5. If violations found: return a ToolMessage with BLOCKED content
       (This is like Strands' event.cancel_tool but as a message)
    6. If all clear: return empty (tool_node will execute)

    WHY THIS WORKS:
    - The LLM sees BLOCKED messages as tool results
    - It naturally adjusts its behavior (steering)
    - The actual tool NEVER executes when rules are violated
    - Rules are code, not prompts - 100% reliable enforcement
    """
    last_message = state["messages"][-1]
    if not last_message.tool_calls:
        return {"messages": []}

    blocked_messages = []
    allowed_calls = []

    for tc in last_message.tool_calls:
        tool_name = tc["name"]

        # Check if this tool has business rules
        if tool_name in TOOL_RULES:
            ctx = build_context(tool_name, tc["args"])
            passed, violations = validate(TOOL_RULES[tool_name], ctx)

            if not passed:
                # BLOCKED: Return a ToolMessage with the violation
                # The LLM will see this and adjust its response
                blocked_messages.append(
                    ToolMessage(
                        content=f"BLOCKED: {', '.join(violations)}",
                        tool_call_id=tc["id"],
                    )
                )
                print(f"    BLOCKED {tool_name}: {violations}")
                continue

        # Tool passed validation (or has no rules)
        allowed_calls.append(tc)

    if blocked_messages:
        # Some tools were blocked - return blocking messages
        # The routing function will send these back to the LLM
        return {"messages": blocked_messages}

    # All tools allowed - return empty, tool_node will handle execution
    return {"messages": []}


def tool_node(state: MessagesState):
    """Execute only the tool calls that passed guardrail validation."""
    # Find the last AIMessage with tool calls
    last_ai = None
    for msg in reversed(state["messages"]):
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            last_ai = msg
            break

    if not last_ai:
        return {"messages": []}

    # Check which tool calls already have ToolMessage responses (blocked ones)
    responded_ids = set()
    for msg in state["messages"]:
        if isinstance(msg, ToolMessage):
            responded_ids.add(msg.tool_call_id)

    # Execute only unblocked tool calls
    results = []
    for tc in last_ai.tool_calls:
        if tc["id"] not in responded_ids:
            tool_fn = tools_by_name[tc["name"]]
            observation = tool_fn.invoke(tc["args"])
            results.append(
                ToolMessage(content=str(observation), tool_call_id=tc["id"])
            )

    return {"messages": results}


def route_after_llm(state: MessagesState) -> Literal["guardrail", "__end__"]:
    """Route: if LLM wants to call tools, go to guardrail first."""
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "guardrail"
    return "__end__"


def route_after_guardrail(state: MessagesState) -> Literal["tool_node", "llm_node"]:
    """
    Route after guardrail:
    - If guardrail blocked something -> back to LLM (with BLOCKED message)
    - If all tools allowed -> execute tools

    The LLM will see the BLOCKED message and either:
    1. Explain the restriction to the user
    2. Try a different approach
    """
    # Check if any recent ToolMessages contain BLOCKED
    for msg in reversed(state["messages"]):
        if isinstance(msg, ToolMessage):
            if "BLOCKED" in msg.content:
                return "llm_node"  # Steering: send back to LLM
            break
    return "tool_node"


# ---------------------------------------------------------------------------
# BUILD THE GRAPH
# ---------------------------------------------------------------------------
graph = StateGraph(MessagesState)

graph.add_node("llm_node", llm_node)
graph.add_node("guardrail", guardrail_node)
graph.add_node("tool_node", tool_node)

# Flow: START -> LLM -> (tools?) -> guardrail -> (blocked?) -> tool_node or LLM
graph.add_edge(START, "llm_node")
graph.add_conditional_edges("llm_node", route_after_llm, ["guardrail", END])
graph.add_conditional_edges(
    "guardrail", route_after_guardrail, ["tool_node", "llm_node"]
)
graph.add_edge("tool_node", "llm_node")

agent_with_guardrails = graph.compile()

# ---------------------------------------------------------------------------
# ALSO CREATE AN AGENT WITHOUT GUARDRAILS FOR COMPARISON
# ---------------------------------------------------------------------------


def create_unguarded_agent():
    """Agent without guardrails - tools execute without validation."""

    def llm_node(state: MessagesState):
        messages = [
            SystemMessage(
                content="You are a hotel booking assistant. Use the available tools to help users."
            )
        ] + state["messages"]
        return {"messages": [model_with_tools.invoke(messages)]}

    def tool_node(state: MessagesState):
        results = []
        for tc in state["messages"][-1].tool_calls:
            tool_fn = tools_by_name[tc["name"]]
            observation = tool_fn.invoke(tc["args"])
            results.append(
                ToolMessage(content=str(observation), tool_call_id=tc["id"])
            )
        return {"messages": results}

    def should_continue(state: MessagesState) -> Literal["tool_node", "__end__"]:
        if state["messages"][-1].tool_calls:
            return "tool_node"
        return "__end__"

    g = StateGraph(MessagesState)
    g.add_node("llm_node", llm_node)
    g.add_node("tool_node", tool_node)
    g.add_edge(START, "llm_node")
    g.add_conditional_edges("llm_node", should_continue, ["tool_node", END])
    g.add_edge("tool_node", "llm_node")
    return g.compile()


unguarded_agent = create_unguarded_agent()

# ---------------------------------------------------------------------------
# RUN THE TESTS
# ---------------------------------------------------------------------------
print("=" * 70)
print("NEUROSYMBOLIC GUARDRAILS WITH LANGGRAPH")
print("=" * 70)
print("\nKey Benefits:")
print("  - Tools are clean: no validation logic mixed in")
print("  - Guardrail node centralizes all validation")
print("  - Symbolic rules enforced at graph level")
print("  - LLM cannot bypass rules (they run as code, not prompts)")
print("=" * 70)

tests = [
    (
        "Confirm booking BK001",
        "Should block - no payment processed yet",
    ),
    (
        "Book Grand Hotel for 15 people from 2026-03-20 to 2026-03-25",
        "Should block - max 10 guests",
    ),
    (
        "Book Grand Hotel for 2 guests from 2026-03-20 to 2026-03-25",
        "Should succeed - valid booking",
    ),
]

for query, expected in tests:
    print(f"\n{'='*70}")
    print(f"Query: {query}")
    print(f"Expected: {expected}")
    print("-" * 70)

    # With guardrails
    print("\n  [WITH GUARDRAILS]")
    result = agent_with_guardrails.invoke(
        {"messages": [HumanMessage(content=query)]}
    )
    output = result["messages"][-1].content
    if "BLOCKED" in str(result):
        print(f"    BLOCKED by symbolic rules")
    print(f"    Response: {output[:200]}...")

    # Without guardrails
    print("\n  [WITHOUT GUARDRAILS]")
    result = unguarded_agent.invoke(
        {"messages": [HumanMessage(content=query)]}
    )
    output = result["messages"][-1].content
    print(f"    Response: {output[:200]}...")

print("\n" + "=" * 70)
print("COMPARISON: Strands Hooks vs LangGraph Guardrail Nodes")
print("=" * 70)
print(
    """
| Aspect            | Strands Hooks                    | LangGraph Guardrail Node        |
|-------------------|----------------------------------|---------------------------------|
| Implementation    | HookProvider subclass            | Regular graph node function     |
| Interception      | BeforeToolCallEvent callback     | Node reads AIMessage.tool_calls |
| Blocking          | event.cancel_tool = "message"    | Return ToolMessage("BLOCKED")   |
| Visibility        | Hidden in hook internals         | Visible in graph structure      |
| Steering          | Framework returns cancel message | LLM sees BLOCKED ToolMessage    |
| Reliability       | 100% (code, not prompts)         | 100% (code, not prompts)        |
"""
)

print("CONCLUSION: Both approaches enforce rules with 100% reliability.")
print("LangGraph makes the guardrail visible as a graph node.")
print("=" * 70)
