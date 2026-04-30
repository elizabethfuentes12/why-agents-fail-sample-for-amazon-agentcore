"""
Demo 03 - Multi-Agent Hallucination Detection with LangGraph
=============================================================

Based on: https://arxiv.org/pdf/2510.19507
(Teaming LLMs to Detect and Mitigate Hallucinations)

KEY CONCEPT: A single agent can hallucinate (claim success for invalid operations).
Multiple agents cross-validate each other: Executor -> Validator -> Critic.

LANGGRAPH ARCHITECTURE:
    Instead of Strands' Swarm (automatic handoffs), we use a StateGraph with
    explicit sequential flow and conditional retry:

    START -> executor -> validator -> critic --[rejected?]--> executor (retry)
                                             +--[approved]--> END

WHAT YOU'LL LEARN:
    1. How to build multi-agent workflows with shared state
    2. How to use custom state beyond just messages
    3. How conditional edges enable retry loops
    4. The difference between Strands Swarm (implicit handoffs) and
       LangGraph StateGraph (explicit graph edges)

KEY DIFFERENCE FROM STRANDS:
    Strands Swarm:
      - Agents hand off to each other using handoff_to_agent() tool
      - The framework manages routing automatically
      - Agents share conversation history implicitly

    LangGraph StateGraph:
      - Routing is defined as graph edges (explicit)
      - State is a typed dictionary shared across all nodes
      - Each node is a function, not a full Agent object
      - More control, more visibility into the flow
"""
import os

os.environ["OTEL_SDK_DISABLED"] = "true"

from dotenv import load_dotenv

load_dotenv()

from langgraph.graph import StateGraph, MessagesState, START, END
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from typing import Literal, Annotated
from typing_extensions import TypedDict
import operator

from tools import search_hotels, book_hotel, get_booking, ALL_TOOLS, BOOKINGS

# ---------------------------------------------------------------------------
# MODEL
# ---------------------------------------------------------------------------
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

# Ground truth for validation
GROUND_TRUTH = {
    "grand_hotel": {"price": 200, "available": True},
    "budget_inn": {"price": 80, "available": True},
    "luxury_resort": {"price": 500, "available": False},
}

# ============================================================================
# PART 1: SINGLE AGENT (baseline - prone to hallucinations)
# ============================================================================
# This is the same pattern from Demo 01: a simple tool-calling loop.
# We use it as baseline to show that a single agent can hallucinate.


def create_single_agent():
    """Create a basic single-agent graph for baseline comparison."""
    model_with_tools = llm.bind_tools(ALL_TOOLS)
    tools_by_name = {t.name: t for t in ALL_TOOLS}

    def llm_node(state: MessagesState):
        messages = [
            SystemMessage(
                content="You are a hotel booking assistant. Use tools to complete requests."
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

    graph = StateGraph(MessagesState)
    graph.add_node("llm_node", llm_node)
    graph.add_node("tool_node", tool_node)
    graph.add_edge(START, "llm_node")
    graph.add_conditional_edges("llm_node", should_continue, ["tool_node", END])
    graph.add_edge("tool_node", "llm_node")
    return graph.compile()


# ============================================================================
# PART 2: MULTI-AGENT VALIDATION (Executor -> Validator -> Critic)
# ============================================================================
# CONCEPT: Multi-agent state
#
# The state holds not just messages, but also:
#   - task: the original user request
#   - executor_result: what the executor did
#   - validation_result: the validator's assessment
#   - critic_result: the critic's final verdict
#   - is_approved: boolean flag for routing
#   - iteration: retry counter (prevents infinite loops)


class MultiAgentState(TypedDict):
    """Shared state across all agents in the validation pipeline.

    messages: Full conversation (accumulated)
    task: The original user request
    executor_result: What the executor agent produced
    validation_result: The validator's assessment (VALID/HALLUCINATION)
    critic_result: The critic's final verdict (APPROVED/REJECTED)
    is_approved: Whether the result passed validation
    iteration: Retry counter to prevent infinite loops
    """

    messages: Annotated[list, operator.add]
    task: str
    executor_result: str
    validation_result: str
    critic_result: str
    is_approved: bool
    iteration: int


# Tool setup for executor
model_with_tools = llm.bind_tools(ALL_TOOLS)
tools_by_name = {t.name: t for t in ALL_TOOLS}


def executor_node(state: MultiAgentState):
    """
    EXECUTOR: The agent that actually does the work.

    This is the only agent with tools. It receives the task,
    calls tools, and produces a result.

    In Strands, this was an Agent with tools that called
    handoff_to_agent("validator") when done.

    In LangGraph, the routing is handled by graph edges,
    so the executor just needs to do its job and return.
    """
    task = state["task"]
    iteration = state.get("iteration", 0)

    # If retrying, include previous feedback
    context = f"Task: {task}"
    if iteration > 0 and state.get("critic_result"):
        context += f"\n\nPREVIOUS ATTEMPT WAS REJECTED. Critic feedback: {state['critic_result']}\nPlease try again more carefully."

    messages = [
        SystemMessage(
            content="You are a hotel booking executor. Use tools to complete the request. "
            "Be precise and only report what the tools actually return. "
            "Never fabricate bookings or invent data."
        ),
        HumanMessage(content=context),
    ]

    # Run the tool-calling loop manually
    # (In a real app, you could use a sub-graph here)
    response = model_with_tools.invoke(messages)
    all_messages = [response]

    # Execute tool calls in a loop until the LLM is done
    max_tool_rounds = 5
    for _ in range(max_tool_rounds):
        if not response.tool_calls:
            break

        tool_results = []
        for tc in response.tool_calls:
            if tc["name"] in tools_by_name:
                observation = tools_by_name[tc["name"]].invoke(tc["args"])
                tool_results.append(
                    ToolMessage(content=str(observation), tool_call_id=tc["id"])
                )

        all_messages.extend(tool_results)
        response = model_with_tools.invoke(messages + all_messages)
        all_messages.append(response)

    # The last message is the executor's final response
    executor_output = response.content if response.content else "No response generated"

    return {
        "messages": [AIMessage(content=f"[EXECUTOR] {executor_output}")],
        "executor_result": executor_output,
    }


def validator_node(state: MultiAgentState):
    """
    VALIDATOR: Reviews the executor's output for accuracy.

    This agent has NO tools - it can only reason about what the
    executor did. It checks:
    - Was the correct tool used?
    - Is the response consistent with the task?
    - Are there signs of hallucination?

    Outputs: VALID or HALLUCINATION with reasons.
    """
    messages = [
        SystemMessage(
            content="You are a booking validator. Review the executor's response and check:\n"
            "1. Was the correct tool used for the request?\n"
            "2. Does the response match the original task?\n"
            "3. Are there any fabricated details or hallucinations?\n"
            "4. If a tool returned an ERROR, did the executor report it honestly?\n\n"
            "Respond with VALID or HALLUCINATION followed by your reasoning."
        ),
        HumanMessage(
            content=f"Original task: {state['task']}\n\nExecutor result: {state['executor_result']}"
        ),
    ]

    response = llm.invoke(messages)
    is_valid = "VALID" in response.content.upper() and "HALLUCINATION" not in response.content.upper()

    return {
        "messages": [AIMessage(content=f"[VALIDATOR] {response.content}")],
        "validation_result": response.content,
        "is_approved": is_valid,
    }


def critic_node(state: MultiAgentState):
    """
    CRITIC: Final review with full context.

    Reviews both the executor's work and the validator's assessment.
    Makes the final call: APPROVED or REJECTED.

    If REJECTED and iteration < max, the flow loops back to executor.
    """
    messages = [
        SystemMessage(
            content="You are the final critic. Review the entire interaction:\n"
            "- The original task\n"
            "- The executor's result\n"
            "- The validator's assessment\n\n"
            "Make your final decision: APPROVED or REJECTED with reasoning.\n"
            "Be strict: if there's any sign of fabricated data, reject it."
        ),
        HumanMessage(
            content=f"Task: {state['task']}\n\n"
            f"Executor result: {state['executor_result']}\n\n"
            f"Validator assessment: {state['validation_result']}"
        ),
    ]

    response = llm.invoke(messages)
    is_approved = "APPROVED" in response.content.upper() and "REJECTED" not in response.content.upper()

    return {
        "messages": [AIMessage(content=f"[CRITIC] {response.content}")],
        "critic_result": response.content,
        "is_approved": is_approved,
        "iteration": state.get("iteration", 0) + 1,
    }


def should_retry(state: MultiAgentState) -> Literal["executor", "__end__"]:
    """
    CONDITIONAL ROUTING: Retry or finish?

    This is where LangGraph shines - explicit control flow.
    In Strands Swarm, the critic was the last agent and couldn't retry.
    Here, we can loop back to the executor if:
      - The result was rejected
      - We haven't exceeded max retries

    DIAGRAM:
        critic --[rejected AND iteration < 3]--> executor (retry)
        critic --[approved OR iteration >= 3]--> END
    """
    if state["is_approved"]:
        return "__end__"
    if state.get("iteration", 0) >= 3:
        return "__end__"  # Max retries reached
    return "executor"


# Build the multi-agent graph
multi_graph = StateGraph(MultiAgentState)

# Add the three agent nodes
multi_graph.add_node("executor", executor_node)
multi_graph.add_node("validator", validator_node)
multi_graph.add_node("critic", critic_node)

# Sequential flow: executor -> validator -> critic
multi_graph.add_edge(START, "executor")
multi_graph.add_edge("executor", "validator")
multi_graph.add_edge("validator", "critic")

# Conditional: critic decides to retry or finish
multi_graph.add_conditional_edges("critic", should_retry, ["executor", END])

multi_agent = multi_graph.compile()

# ============================================================================
# RUN THE TESTS
# ============================================================================
single_agent = create_single_agent()

print("=" * 70)
print("HALLUCINATION DETECTION TEST: Single vs Multi-Agent (LangGraph)")
print("=" * 70)

# TEST 1: Valid booking - both should succeed
print("\n[TEST 1] Single Agent - Valid Booking")
result = single_agent.invoke(
    {"messages": [HumanMessage(content="Book grand_hotel for John for 2 nights")]}
)
print(f"  Response: {result['messages'][-1].content[:150]}...")

# TEST 2: Invalid hotel - single agent may hallucinate
print("\n[TEST 2] Single Agent - Invalid Hotel (the_ritz_paris doesn't exist)")
result = single_agent.invoke(
    {"messages": [HumanMessage(content="Book the_ritz_paris for Sarah for 3 nights")]}
)
print(f"  Response: {result['messages'][-1].content[:200]}...")

# TEST 3: Multi-agent valid booking
print("\n[TEST 3] Multi-Agent - Valid Booking with Validation")
# Reset bookings for clean test
BOOKINGS.clear()
result = multi_agent.invoke(
    {
        "messages": [],
        "task": "Book grand_hotel for John for 2 nights",
        "executor_result": "",
        "validation_result": "",
        "critic_result": "",
        "is_approved": False,
        "iteration": 0,
    }
)
# Show the flow of agents
agent_flow = [
    m.content.split("]")[0] + "]"
    for m in result["messages"]
    if isinstance(m, AIMessage) and m.content.startswith("[")
]
print(f"  Flow: {' -> '.join(agent_flow)}")
print(f"  Approved: {result['is_approved']}")
print(f"  Iterations: {result['iteration']}")

# TEST 4: Multi-agent invalid hotel detection
print("\n[TEST 4] Multi-Agent - Invalid Hotel Detection")
result = multi_agent.invoke(
    {
        "messages": [],
        "task": "Book the_ritz_paris for Sarah for 3 nights",
        "executor_result": "",
        "validation_result": "",
        "critic_result": "",
        "is_approved": False,
        "iteration": 0,
    }
)
agent_flow = [
    m.content.split("]")[0] + "]"
    for m in result["messages"]
    if isinstance(m, AIMessage) and m.content.startswith("[")
]
print(f"  Flow: {' -> '.join(agent_flow)}")
print(f"  Approved: {result['is_approved']}")
print(f"  Final verdict: {result['critic_result'][:200]}...")

# TEST 5: Unavailable hotel
print("\n[TEST 5] Multi-Agent - Unavailable Hotel")
result = multi_agent.invoke(
    {
        "messages": [],
        "task": "Book luxury_resort for Bob for 1 night",
        "executor_result": "",
        "validation_result": "",
        "critic_result": "",
        "is_approved": False,
        "iteration": 0,
    }
)
agent_flow = [
    m.content.split("]")[0] + "]"
    for m in result["messages"]
    if isinstance(m, AIMessage) and m.content.startswith("[")
]
print(f"  Flow: {' -> '.join(agent_flow)}")
print(f"  Approved: {result['is_approved']}")

print("\n" + "=" * 70)
print("CONCLUSION:")
print("- Single agent may fabricate responses for invalid hotels")
print("- Multi-agent system validates and catches hallucinations")
print("- Executor -> Validator -> Critic provides cross-validation")
print("- LangGraph adds retry capability that Strands Swarm doesn't have")
print("=" * 70)
