"""
Tool Registry - FAISS semantic search over tools (LangGraph Version)
====================================================================

CONCEPT: Semantic tool filtering
    Instead of giving 29 tools to the LLM (wasting tokens and confusing it),
    we use embeddings to find the 3 most relevant tools per query.

HOW IT WORKS:
    1. build_index() - Embeds name+docstring of each tool, builds FAISS index
    2. search_tools() - Embeds the user query, finds the k nearest tools
    3. get_scores() - Returns scores for debugging

DIFFERENCE FROM STRANDS:
    In Strands, swap_tools() modifies agent.tool_registry directly.
    In LangGraph, we use bind_tools() dynamically on each iteration.
    There's no swap_tools() because the graph uses a filtering node
    that selects tools before calling the LLM.
"""
import faiss
from sentence_transformers import SentenceTransformer
from typing import List, Callable

_model = None
_index = None
_tools = []


def _get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


def build_index(tools: List[Callable]):
    """Build FAISS index from tool names + docstrings.

    Each tool becomes a text "name: description" and is embedded into
    a 384-dimensional vector. FAISS enables fast similarity search
    using L2 (Euclidean) distance.
    """
    global _index, _tools
    _tools = tools

    # LangChain tools have .name and .description (not __name__ and __doc__)
    texts = [f"{t.name}: {t.description}" for t in tools]

    model = _get_model()
    embeddings = model.encode(texts)

    _index = faiss.IndexFlatL2(embeddings.shape[1])
    _index.add(embeddings.astype("float32"))

    print(f"Indexed {len(tools)} tools")


def search_tools(query: str, top_k: int = 3) -> List[Callable]:
    """Find most relevant tools for a query using semantic similarity."""
    global _index, _tools

    model = _get_model()
    emb = model.encode([query])

    _, indices = _index.search(emb.astype("float32"), top_k)

    return [_tools[i] for i in indices[0]]


def get_scores(query: str, top_k: int = 10) -> List[dict]:
    """Get tool similarity scores for debugging.

    score = 1/(1+distance): closer to 1 = more relevant.
    """
    global _index, _tools

    model = _get_model()
    emb = model.encode([query])

    distances, indices = _index.search(emb.astype("float32"), min(top_k, len(_tools)))

    return [
        {"name": _tools[i].name, "score": 1 / (1 + d), "doc": _tools[i].description}
        for i, d in zip(indices[0], distances[0])
    ]
