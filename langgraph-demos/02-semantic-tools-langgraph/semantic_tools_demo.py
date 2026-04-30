"""
Demo 02 - Semantic Tool Selection with LangGraph
==================================================

KEY CONCEPT: Instead of giving 29 tools to the LLM (expensive in tokens and
error-prone), we use FAISS to find the 3 most relevant tools per query.

LANGGRAPH ARCHITECTURE:
    The graph has an extra node at the start that filters tools BEFORE calling the LLM:

    START -> filter_tools -> llm_node -> (tool_calls?) -> tool_node -> llm_node -> END

WHAT YOU'LL LEARN:
    1. How to create custom state with TypedDict (beyond just MessagesState)
    2. How to do dynamic bind_tools() (different tools per query)
    3. How to measure token reduction with semantic filtering
    4. The "preprocessing" pattern before the LLM call
"""
import os

os.environ["OTEL_SDK_DISABLED"] = "true"

from dotenv import load_dotenv

load_dotenv()

from langgraph.graph import StateGraph, START, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage, AnyMessage
from typing import Literal, Annotated
from typing_extensions import TypedDict
import operator

from enhanced_tools import ALL_TOOLS
from registry import build_index, search_tools, get_scores

# ---------------------------------------------------------------------------
# LLM MODEL
# ---------------------------------------------------------------------------
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

# ---------------------------------------------------------------------------
# BUILD TOOL INDEX
# ---------------------------------------------------------------------------
# Done once. Embeds all 29 tools and builds the FAISS index.
build_index(ALL_TOOLS)

# ---------------------------------------------------------------------------
# CUSTOM STATE
# ---------------------------------------------------------------------------
# CONCEPT: TypedDict with Annotated
#
# In LangGraph, state is a typed dictionary. Each field can have a "reducer"
# that defines how values are combined when a node returns.
#
#   Annotated[list, operator.add]  -> ACCUMULATES (append). Each return is added.
#   Without Annotated              -> REPLACES. Each return overwrites the previous.
#
# This is key to understanding LangGraph:
#   - messages uses operator.add because we want the FULL conversation
#   - selected_tools is replaced because we want the tools for the current query
#   - query is replaced because it's the current user query


class SemanticToolState(TypedDict):
    """Graph state with semantic tool filtering.

    messages: Full conversation (accumulated with operator.add)
    selected_tools: Tools selected for the current query (replaced)
    query: The current user query (replaced)
    """

    messages: Annotated[list[AnyMessage], operator.add]
    selected_tools: list[str]  # names of selected tools
    query: str


# ---------------------------------------------------------------------------
# GRAPH NODES
# ---------------------------------------------------------------------------
# Dictionary for looking up tools by name
all_tools_by_name = {t.name: t for t in ALL_TOOLS}


def filter_tools_node(state: SemanticToolState):
    """
    SEMANTIC FILTERING NODE (the new part in this demo)

    This node runs BEFORE the LLM. It finds the 3 most relevant tools
    for the query using embeddings + FAISS.

    HOW IT WORKS:
    1. Takes the query from state
    2. Embeds it with SentenceTransformer
    3. Finds the 3 nearest tool vectors in FAISS
    4. Returns those tool names

    This reduces tokens from ~1,550 (29 tools x ~50 tokens) to ~150 (3 tools x ~50).
    """
    query = state["query"]
    selected = search_tools(query, top_k=3)
    tool_names = [t.name for t in selected]

    print(f"  Selected tools: {tool_names}")

    return {"selected_tools": tool_names}


def llm_node(state: SemanticToolState):
    """
    LLM NODE WITH DYNAMIC TOOLS

    KEY DIFFERENCE from Demo 01:
    Here we call bind_tools() with ONLY the selected tools,
    not all 29. The LLM only sees 3 tools in its context.

    In Strands this was done with swap_tools(agent, new_tools).
    In LangGraph, we create a new bind_tools() on each call.
    """
    # Get only the selected tools
    active_tools = [all_tools_by_name[name] for name in state["selected_tools"]]

    # Dynamic bind_tools - ONLY the filtered tools
    model_with_tools = llm.bind_tools(active_tools)

    messages = [
        SystemMessage(
            content="You are a travel assistant. Use the available tools to help the user."
        )
    ] + state["messages"]

    response = model_with_tools.invoke(messages)
    return {"messages": [response]}


def tool_node(state: SemanticToolState):
    """Execute the tools the LLM requested."""
    results = []
    for tc in state["messages"][-1].tool_calls:
        tool_fn = all_tools_by_name[tc["name"]]
        observation = tool_fn.invoke(tc["args"])
        results.append(ToolMessage(content=str(observation), tool_call_id=tc["id"]))
    return {"messages": results}


def should_continue(state: SemanticToolState) -> Literal["tool_node", "__end__"]:
    """If the LLM wants to use tools, execute them. Otherwise, finish."""
    if state["messages"][-1].tool_calls:
        return "tool_node"
    return "__end__"


# ---------------------------------------------------------------------------
# BUILD THE GRAPH
# ---------------------------------------------------------------------------
# DIAGRAM:
#   START -> filter_tools -> llm_node --[tool_calls?]--> tool_node -> llm_node
#                                      \--[no tools]---> END

graph = StateGraph(SemanticToolState)

graph.add_node("filter_tools", filter_tools_node)
graph.add_node("llm_node", llm_node)
graph.add_node("tool_node", tool_node)

# Flow: START -> filter -> LLM -> (decide) -> tools or END
graph.add_edge(START, "filter_tools")
graph.add_edge("filter_tools", "llm_node")
graph.add_conditional_edges("llm_node", should_continue, ["tool_node", END])
graph.add_edge("tool_node", "llm_node")

semantic_agent = graph.compile()

# ---------------------------------------------------------------------------
# ALSO CREATE A "TRADITIONAL" AGENT (with all tools) FOR COMPARISON
# ---------------------------------------------------------------------------
traditional_model = llm.bind_tools(ALL_TOOLS)


class TraditionalState(TypedDict):
    messages: Annotated[list[AnyMessage], operator.add]


def traditional_llm_node(state: TraditionalState):
    messages = [
        SystemMessage(
            content="You are a travel assistant. Use the available tools to help the user."
        )
    ] + state["messages"]
    return {"messages": [traditional_model.invoke(messages)]}


def traditional_tool_node(state: TraditionalState):
    results = []
    for tc in state["messages"][-1].tool_calls:
        tool_fn = all_tools_by_name[tc["name"]]
        observation = tool_fn.invoke(tc["args"])
        results.append(ToolMessage(content=str(observation), tool_call_id=tc["id"]))
    return {"messages": results}


def traditional_should_continue(
    state: TraditionalState,
) -> Literal["tool_node", "__end__"]:
    if state["messages"][-1].tool_calls:
        return "tool_node"
    return "__end__"


trad_graph = StateGraph(TraditionalState)
trad_graph.add_node("llm_node", traditional_llm_node)
trad_graph.add_node("tool_node", traditional_tool_node)
trad_graph.add_edge(START, "llm_node")
trad_graph.add_conditional_edges(
    "llm_node", traditional_should_continue, ["tool_node", END]
)
trad_graph.add_edge("tool_node", "llm_node")
traditional_agent = trad_graph.compile()

# ---------------------------------------------------------------------------
# RUN COMPARISON
# ---------------------------------------------------------------------------
print("=" * 70)
print("SEMANTIC TOOL SELECTION: Traditional vs Semantic (LangGraph)")
print("=" * 70)
print(f"\nTotal tools available: {len(ALL_TOOLS)}")
print(f"Estimated tokens per tool: ~50")
print(f"Traditional: ~{len(ALL_TOOLS) * 50} tokens for tool definitions")
print(f"Semantic (top-3): ~{3 * 50} tokens for tool definitions")
print(f"Token reduction: ~{((len(ALL_TOOLS) - 3) / len(ALL_TOOLS) * 100):.0f}%")

queries = [
    "Book a hotel in Rome for Alice",
    "What's the weather in Paris?",
    "Find flights from NYC to London",
    "How much is 100 USD in EUR?",
    "Check if Grand Hotel has rooms for March 15 to March 20",
    "Cancel my hotel reservation",
]

for query in queries:
    print(f"\n{'='*70}")
    print(f"Query: {query}")
    print("=" * 70)

    # Show tool ranking
    scores = get_scores(query, top_k=5)
    print("\n  Top-5 tool scores:")
    for s in scores:
        print(f"    {s['score']:.3f} | {s['name']}: {s['doc'][:60]}...")

    # Run with semantic agent
    print("\n  [SEMANTIC - 3 tools]")
    result = semantic_agent.invoke(
        {"messages": [HumanMessage(content=query)], "query": query, "selected_tools": []}
    )
    response_text = result["messages"][-1].content
    print(f"  Response: {response_text[:150]}...")
    print(
        f"  Tools used: {[tc['name'] for m in result['messages'] if hasattr(m, 'tool_calls') and m.tool_calls for tc in m.tool_calls]}"
    )

    # Run with traditional agent
    print(f"\n  [TRADITIONAL - {len(ALL_TOOLS)} tools]")
    result = traditional_agent.invoke({"messages": [HumanMessage(content=query)]})
    response_text = result["messages"][-1].content
    print(f"  Response: {response_text[:150]}...")
    print(
        f"  Tools used: {[tc['name'] for m in result['messages'] if hasattr(m, 'tool_calls') and m.tool_calls for tc in m.tool_calls]}"
    )

print("\n" + "=" * 70)
print("KEY INSIGHTS")
print("=" * 70)
print(
    """
1. Semantic filtering reduces token usage by ~89%
2. The LLM sees only relevant tools, reducing confusion
3. Ambiguous generic tools (search, check, get_info) are filtered out
4. Domain-specific tools rank higher for domain-specific queries
"""
)
