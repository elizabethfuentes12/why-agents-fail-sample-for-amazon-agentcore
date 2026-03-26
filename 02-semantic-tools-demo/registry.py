"""
Tool Registry - FAISS semantic search over tools
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
        _model = SentenceTransformer('all-MiniLM-L6-v2')
    return _model

def build_index(tools: List[Callable]):
    """Build FAISS index from tool docstrings"""
    global _index, _tools
    _tools = tools
    
    # Use name + docstring for embedding
    texts = [f"{t.__name__}: {t.__doc__}" for t in tools]
    
    model = _get_model()
    embeddings = model.encode(texts)
    
    _index = faiss.IndexFlatL2(embeddings.shape[1])
    _index.add(embeddings.astype('float32'))
    
    print(f"✅ Indexed {len(tools)} tools")

def search_tools(query: str, top_k: int = 3) -> List[Callable]:
    """Find most relevant tools for a query"""
    global _index, _tools
    
    model = _get_model()
    emb = model.encode([query])
    
    _, indices = _index.search(emb.astype('float32'), top_k)
    
    return [_tools[i] for i in indices[0]]

def swap_tools(agent, new_tools: List[Callable]):
    """Swap tools in a live agent without losing conversation memory.
    
    Clears the agent's tool_registry and re-registers only the given tools.
    Since get_all_tools_config() is called each event loop cycle, the agent
    will see the new tools on the next call.
    """
    reg = agent.tool_registry
    reg.registry.clear()
    reg.dynamic_tools.clear()
    for t in new_tools:
        reg.register_tool(t)


def get_scores(query: str, top_k: int = 10) -> List[dict]:
    """Get tool scores for debugging"""
    global _index, _tools
    
    model = _get_model()
    emb = model.encode([query])
    
    distances, indices = _index.search(emb.astype('float32'), min(top_k, len(_tools)))
    
    return [
        {'name': _tools[i].__name__, 'score': 1/(1+d), 'doc': _tools[i].__doc__}
        for i, d in zip(indices[0], distances[0])
    ]
