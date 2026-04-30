"""
Demo 05 - Block vs Steer: Agent Control with LangGraph
========================================================

Compares two guardrail approaches on the SAME booking scenario:
  Test 1 — Block: Guardrail node blocks violations (Demo 04 pattern)
  Test 2 — Steer: Steering node guides the agent to self-correct (new pattern)

Same tools, same model, same query. Only the guardrail strategy changes.

KEY CONCEPT: STEER vs DENY (Block)
    DENY/Block: Rule violated -> tool call blocked -> task FAILS -> user must retry
    STEER:      Rule violated -> agent receives guidance -> agent self-corrects -> task COMPLETES

    Example: "Book for 15 guests" (max is 10)
      Block:  "I cannot proceed, the limit is 10 guests" (task stopped)
      Steer:  "Adjusted to 10 guests. Booking confirmed." (task completed)

LANGGRAPH ARCHITECTURE:
    The steering agent adds a NEW node that evaluates the LLM's text output
    BEFORE tool calls are executed. If a steer control matches, it injects
    guidance back into the conversation and routes back to the LLM.

    Block pattern (Demo 04):
        llm_node -> guardrail -> [blocked?] -> BACK TO LLM (with error)
                                            -> tool_node

    Steer pattern (Demo 05):
        llm_node -> steer_check -> [steer?] -> BACK TO LLM (with guidance)
                                            -> guardrail -> [deny?] -> BACK TO LLM
                                                                    -> tool_node

WHAT YOU'LL LEARN:
    1. How STEER controls evaluate LLM text output (not tool params)
    2. How to inject steering guidance as a SystemMessage
    3. The difference between blocking (task fails) and steering (task completes)
    4. How this maps to DynamoDB rules in production (Demo 06)

RELATION TO DEMO 06 (PRODUCTION):
    Here, controls are Python objects in controls.py.
    In Demo 06, they become DynamoDB items:
        {"rule_id": "max-guests", "steer_message": "Reduce to 10...", ...}
    The validate_booking_rules Lambda evaluates them the same way.
"""
import os
import time

os.environ["OTEL_SDK_DISABLED"] = "true"

from dotenv import load_dotenv

load_dotenv()

from langgraph.graph import StateGraph, START, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import (
    SystemMessage,
    HumanMessage,
    AIMessage,
    ToolMessage,
    AnyMessage,
)
from typing import Literal, Annotated
from typing_extensions import TypedDict
import operator

from tools import ALL_TOOLS, STATE
from controls import evaluate_controls

# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------
if not os.getenv("OPENAI_API_KEY"):
    raise ValueError(
        "OPENAI_API_KEY not set. Get your API key from https://platform.openai.com/api-keys "
        "then either: 1) Add OPENAI_API_KEY=your-key to a .env file, or "
        "2) Run: export OPENAI_API_KEY=your-key"
    )

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
model_with_tools = llm.bind_tools(ALL_TOOLS)
tools_by_name = {t.name: t for t in ALL_TOOLS}

QUERY = "Book Grand Hotel for 15 guests from 2026-05-01 to 2026-05-03"

# System prompt that makes the LLM describe the booking BEFORE calling the tool.
# This is needed so steer controls can detect "15 guests" in the LLM text output.
PROMPT = (
    "You are a hotel booking assistant. "
    "When booking, first describe what you will book (hotel, guests, dates) "
    "then call the tool."
)

# ============================================================================
# APPROACH 1: BLOCK (Demo 04 pattern — guardrail blocks violations)
# ============================================================================


class BlockState(TypedDict):
    messages: Annotated[list[AnyMessage], operator.add]


def block_llm_node(state: BlockState):
    messages = [SystemMessage(content=PROMPT)] + state["messages"]
    return {"messages": [model_with_tools.invoke(messages)]}


def block_guardrail_node(state: BlockState):
    """Guardrail that BLOCKS tool calls exceeding 10 guests.

    This is the Demo 04 pattern: inspect tool_call params, block if invalid.
    The LLM sees "BLOCKED" and reports failure to the user.
    """
    last_message = state["messages"][-1]
    if not last_message.tool_calls:
        return {"messages": []}

    blocked_messages = []
    for tc in last_message.tool_calls:
        if tc["name"] == "book_hotel":
            guests = tc["args"].get("guests", 1)
            if guests > 10:
                blocked_messages.append(
                    ToolMessage(
                        content=f"BLOCKED: {guests} guests exceeds maximum of 10. Cannot proceed.",
                        tool_call_id=tc["id"],
                    )
                )
                print(f"    BLOCKED: {guests} guests > 10")

    if blocked_messages:
        return {"messages": blocked_messages}
    return {"messages": []}


def block_tool_node(state: BlockState):
    last_ai = None
    for msg in reversed(state["messages"]):
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            last_ai = msg
            break
    if not last_ai:
        return {"messages": []}

    responded_ids = {
        msg.tool_call_id for msg in state["messages"] if isinstance(msg, ToolMessage)
    }

    results = []
    for tc in last_ai.tool_calls:
        if tc["id"] not in responded_ids:
            tool_fn = tools_by_name[tc["name"]]
            observation = tool_fn.invoke(tc["args"])
            results.append(
                ToolMessage(content=str(observation), tool_call_id=tc["id"])
            )
    return {"messages": results}


def block_route_after_llm(state: BlockState) -> Literal["guardrail", "__end__"]:
    last = state["messages"][-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "guardrail"
    return "__end__"


def block_route_after_guardrail(
    state: BlockState,
) -> Literal["tool_node", "llm_node"]:
    for msg in reversed(state["messages"]):
        if isinstance(msg, ToolMessage):
            if "BLOCKED" in msg.content:
                return "llm_node"
            break
    return "tool_node"


# Build block agent
block_graph = StateGraph(BlockState)
block_graph.add_node("llm_node", block_llm_node)
block_graph.add_node("guardrail", block_guardrail_node)
block_graph.add_node("tool_node", block_tool_node)
block_graph.add_edge(START, "llm_node")
block_graph.add_conditional_edges(
    "llm_node", block_route_after_llm, ["guardrail", END]
)
block_graph.add_conditional_edges(
    "guardrail", block_route_after_guardrail, ["tool_node", "llm_node"]
)
block_graph.add_edge("tool_node", "llm_node")
block_agent = block_graph.compile()


# ============================================================================
# APPROACH 2: STEER (new pattern — agent self-corrects)
# ============================================================================
# KEY DIFFERENCE: Instead of blocking tool calls, we evaluate the LLM's
# TEXT OUTPUT and send guidance BEFORE it makes the tool call.
#
# Flow:
#   LLM says "I'll book for 15 guests..."
#   -> steer_check detects "15 guests" in text
#   -> injects guidance: "Reduce to 10, retry..."
#   -> LLM retries with 10 guests
#   -> guardrail checks tool params (DENY controls)
#   -> tool executes
#   -> task completes


class SteerState(TypedDict):
    """State for the steering agent.

    messages: Full conversation
    steer_count: Number of times steering was applied (for tracking)
    steered_this_turn: Flag set by steer_check, cleared after routing decision
    """

    messages: Annotated[list[AnyMessage], operator.add]
    steer_count: int
    steered_this_turn: bool


def steer_llm_node(state: SteerState):
    """LLM node - same as block agent."""
    messages = [SystemMessage(content=PROMPT)] + state["messages"]
    return {"messages": [model_with_tools.invoke(messages)]}


def steer_check_node(state: SteerState):
    """
    STEERING CHECK NODE — The core innovation of Demo 05.

    This node evaluates the LLM's TEXT OUTPUT (not tool params) against
    STEER controls. If a violation is detected in the text, it:
    1. Removes the LLM's message (so the tool calls don't execute)
    2. Injects a guidance SystemMessage
    3. Routes back to the LLM for a retry

    HOW THIS DIFFERS FROM DEMO 04 (guardrail):
      Demo 04: Inspects tool_call params -> blocks with ToolMessage("BLOCKED")
      Demo 05: Inspects LLM text output -> steers with SystemMessage(guidance)

    WHY EVALUATE TEXT, NOT TOOL PARAMS?
      The LLM describes "15 guests" in text BEFORE making the tool call.
      Steering catches it early and redirects, so the tool call never happens
      with wrong params. The LLM retries with corrected params (10 guests).

    IN PRODUCTION (Demo 06):
      This is the validate_booking_rules Lambda checking DynamoDB rules.
      If steer_message is set, it returns guidance; agent retries.
    """
    last_message = state["messages"][-1]

    # Only evaluate AIMessages that have text content
    if not isinstance(last_message, AIMessage):
        return {"messages": [], "steered_this_turn": False}

    text_content = last_message.content or ""

    # Evaluate against STEER controls (scope=llm_output)
    control, match = evaluate_controls(text_content, scope="llm_output")

    if control and control.decision == "steer":
        print(f"    STEER: Detected '{match.group()}' -> {control.fail_message}")
        print(f"    Guidance: {control.steer_message[:80]}...")

        # IMPORTANT: OpenAI requires that every AIMessage with tool_calls
        # has matching ToolMessage responses. We must:
        # 1. Respond to each tool_call with a CANCELLED ToolMessage
        # 2. Add guidance as a HumanMessage (not SystemMessage, which would
        #    break the message ordering that OpenAI expects)
        #
        # The LLM will see the CANCELLED results + guidance and retry.
        abandon_messages = []
        if last_message.tool_calls:
            for tc in last_message.tool_calls:
                abandon_messages.append(
                    ToolMessage(
                        content="CANCELLED: Steering applied, retrying with corrected parameters.",
                        tool_call_id=tc["id"],
                    )
                )

        # Use HumanMessage for guidance so OpenAI message ordering stays valid
        # (SystemMessage in the middle of a conversation can cause issues)
        guidance = HumanMessage(
            content=(
                f"STEERING GUIDANCE: {control.steer_message}\n"
                f"Violation detected: {control.fail_message}\n"
                "Please adjust your response and try again."
            )
        )

        return {
            "messages": abandon_messages + [guidance],
            "steer_count": state.get("steer_count", 0) + 1,
            "steered_this_turn": True,
        }

    # No steer control matched — proceed normally
    return {"messages": [], "steered_this_turn": False}


def steer_guardrail_node(state: SteerState):
    """DENY guardrail — checks tool params for hard violations.

    This is the same as Demo 04's guardrail, but only handles DENY controls.
    STEER controls were already handled by steer_check_node.
    """
    last_ai = None
    for msg in reversed(state["messages"]):
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            last_ai = msg
            break
    if not last_ai:
        return {"messages": []}

    blocked_messages = []
    for tc in last_ai.tool_calls:
        # Evaluate DENY controls on tool input
        input_text = str(tc["args"])
        control, match = evaluate_controls(
            input_text, scope="tool_input", tool_name=tc["name"]
        )

        if control and control.decision == "deny":
            # Check if payment exists (for deny-no-payment control)
            booking_id = tc["args"].get("booking_id", "")
            if booking_id and booking_id not in STATE["payments"]:
                blocked_messages.append(
                    ToolMessage(
                        content=f"DENIED: {control.fail_message}",
                        tool_call_id=tc["id"],
                    )
                )
                print(f"    DENIED: {control.fail_message}")

    if blocked_messages:
        return {"messages": blocked_messages}
    return {"messages": []}


def steer_tool_node(state: SteerState):
    """Execute only tool calls that weren't blocked or steered."""
    last_ai = None
    for msg in reversed(state["messages"]):
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            last_ai = msg
            break
    if not last_ai:
        return {"messages": []}

    responded_ids = {
        msg.tool_call_id for msg in state["messages"] if isinstance(msg, ToolMessage)
    }

    results = []
    for tc in last_ai.tool_calls:
        if tc["id"] not in responded_ids:
            tool_fn = tools_by_name[tc["name"]]
            observation = tool_fn.invoke(tc["args"])
            results.append(
                ToolMessage(content=str(observation), tool_call_id=tc["id"])
            )
    return {"messages": results}


def steer_route_after_llm(state: SteerState) -> Literal["steer_check", "__end__"]:
    """After LLM: always go to steer check (evaluates text output)."""
    last = state["messages"][-1]
    # If LLM produced any content or tool calls, check for steering
    if isinstance(last, AIMessage):
        return "steer_check"
    return "__end__"


def steer_route_after_check(
    state: SteerState,
) -> Literal["guardrail", "llm_node", "__end__"]:
    """After steer check: if steered, back to LLM. Otherwise, to guardrail.

    Uses the steered_this_turn flag (set by steer_check_node) to decide.
    IMPORTANT: Only check the MOST RECENT AIMessage for tool_calls, not
    historical ones — otherwise old AIMessages with tool_calls cause loops.
    """
    if state.get("steered_this_turn", False):
        return "llm_node"  # Retry with guidance

    # Find the most recent AIMessage (the one steer_check just evaluated)
    for msg in reversed(state["messages"]):
        if isinstance(msg, AIMessage):
            if msg.tool_calls:
                return "guardrail"  # Check DENY controls on tool params
            return "__end__"  # No tool calls, LLM gave a final text response
        # Skip non-AI messages added by steer_check (empty return)
        break

    return "__end__"


def steer_route_after_guardrail(
    state: SteerState,
) -> Literal["tool_node", "llm_node"]:
    """After guardrail: if denied, back to LLM. Otherwise execute tools."""
    for msg in reversed(state["messages"]):
        if isinstance(msg, ToolMessage):
            if "DENIED" in msg.content:
                return "llm_node"
            break
    return "tool_node"


# Build steer agent
#
# GRAPH DIAGRAM:
#   START -> llm_node -> steer_check -> [steered?] -> llm_node (retry with guidance)
#                                    \-> guardrail -> [denied?] -> llm_node (report error)
#                                                  \-> tool_node -> llm_node
#                     \-> END (no tool calls, final text response)
steer_graph = StateGraph(SteerState)

steer_graph.add_node("llm_node", steer_llm_node)
steer_graph.add_node("steer_check", steer_check_node)
steer_graph.add_node("guardrail", steer_guardrail_node)
steer_graph.add_node("tool_node", steer_tool_node)

steer_graph.add_edge(START, "llm_node")
steer_graph.add_conditional_edges(
    "llm_node", steer_route_after_llm, ["steer_check", END]
)
steer_graph.add_conditional_edges(
    "steer_check", steer_route_after_check, ["guardrail", "llm_node", END]
)
steer_graph.add_conditional_edges(
    "guardrail", steer_route_after_guardrail, ["tool_node", "llm_node"]
)
steer_graph.add_edge("tool_node", "llm_node")

steer_agent = steer_graph.compile()


# ============================================================================
# RUN THE TESTS
# ============================================================================
def run_test_1_block():
    """Test 1: Block approach — guardrail blocks, task fails."""
    print("\n" + "=" * 70)
    print("TEST 1: BLOCK (guardrail blocks violations)")
    print("=" * 70)
    print(f"Query: {QUERY}\n")

    start = time.time()
    result = block_agent.invoke({"messages": [HumanMessage(content=QUERY)]})
    elapsed = time.time() - start

    output = result["messages"][-1].content
    print(f"\n  Time: {elapsed:.1f}s")
    print(f"  Response: {output[:300]}")

    blocked = any(
        isinstance(m, ToolMessage) and "BLOCKED" in m.content
        for m in result["messages"]
    )
    if blocked:
        print("  Result: BLOCKED — task failed, user must retry")
        return {"time": elapsed, "outcome": "blocked"}
    elif "SUCCESS" in output and "15 guests" in output:
        print("  Result: Agent bypassed the guardrail (unexpected)")
        return {"time": elapsed, "outcome": "bypassed"}
    else:
        print("  Result: Agent found a workaround")
        return {"time": elapsed, "outcome": "workaround"}


def run_test_2_steer():
    """Test 2: Steer approach — agent self-corrects, task completes."""
    print("\n" + "=" * 70)
    print("TEST 2: STEER (agent self-corrects with guidance)")
    print("=" * 70)
    print(f"Query: {QUERY}\n")

    # Reset state for clean test
    STATE["bookings"] = {
        "BK001": {
            "hotel": "Grand Hotel",
            "check_in": "2026-04-15",
            "guests": 2,
            "total": 400,
        }
    }
    STATE["payments"] = {}

    start = time.time()
    result = steer_agent.invoke(
        {"messages": [HumanMessage(content=QUERY)], "steer_count": 0, "steered_this_turn": False}
    )
    elapsed = time.time() - start

    output = result["messages"][-1].content
    steer_count = result.get("steer_count", 0)

    print(f"\n  Time: {elapsed:.1f}s")
    print(f"  Steered: {steer_count} time(s)")
    print(f"  Response: {output[:300]}")

    if "SUCCESS" in str(result) or "BK" in output:
        print("  Result: SELF-CORRECTED — task completed with adjusted guest count")
        return {"time": elapsed, "steered": steer_count, "outcome": "self-corrected"}
    else:
        print("  Result: Check output")
        return {"time": elapsed, "steered": steer_count, "outcome": "unclear"}


if __name__ == "__main__":
    print("=" * 70)
    print("  BLOCK vs STEER — Same query, different guardrail strategy")
    print("  Query: " + QUERY)
    print("=" * 70)

    r1 = run_test_1_block()
    r2 = run_test_2_steer()

    print(f"\n{'='*70}")
    print(f"{'Approach':<35} {'Time':>8} {'Outcome':>20}")
    print("-" * 65)
    print(f"{'Block (Demo 04 pattern)':<35} {r1['time']:>6.1f}s {r1['outcome']:>20}")
    print(f"{'Steer (Demo 05 pattern)':<35} {r2['time']:>6.1f}s {r2['outcome']:>20}")

    print(f"\n{'='*70}")
    print("PROGRESSION TO PRODUCTION (Demo 06)")
    print("=" * 70)
    print(
        """
| Aspect         | Demo 04 (Block)      | Demo 05 (Steer)      | Demo 06 (Production)     |
|----------------|----------------------|----------------------|--------------------------|
| Where rules    | rules.py (Python)    | controls.py (Python) | DynamoDB items           |
| live           |                      |                      |                          |
| Rule format    | Python dataclasses   | Control dataclasses  | JSON items               |
| Enforcement    | Guardrail node       | Steer + guardrail    | Lambda + steering        |
|                | (blocks tool calls)  | (guides LLM retry)   | (same steer pattern)     |
| On violation   | Task FAILS           | Task COMPLETES       | Task COMPLETES           |
| Change rules   | Edit code, restart   | Edit controls.py     | Update DynamoDB (instant)|
"""
    )
