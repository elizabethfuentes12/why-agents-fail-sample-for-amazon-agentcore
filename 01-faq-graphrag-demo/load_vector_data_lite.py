"""
Build LITE FAISS vector store from hotel FAQ documents.

LITE VERSION: Processes only 30 documents (10% of full dataset) for faster testing.
This matches the lite version of the Neo4j graph for fair comparison.
"""
import faiss
import json
from pathlib import Path
from sentence_transformers import SentenceTransformer

# LITE: Process only first 30 documents
MAX_DOCS = 30


def load_to_vector_store():
    model = SentenceTransformer('all-MiniLM-L6-v2')
    
    documents = []
    data_dir = Path("data")
    
    # Load only first 30 documents
    for faq_file in sorted(data_dir.glob("*.txt"))[:MAX_DOCS]:
        with open(faq_file, 'r', encoding='utf-8') as f:
            text = f.read()
            documents.append({
                'filename': faq_file.name,
                'text': text
            })
    
    print(f"🚀 LITE MODE: Loading {len(documents)} FAQ documents (10% of full dataset)...")
    
    texts = [doc['text'] for doc in documents]
    embeddings = model.encode(texts, show_progress_bar=True)
    
    dimension = embeddings.shape[1]
    index = faiss.IndexFlatL2(dimension)
    index.add(embeddings.astype('float32'))
    
    # Save with _lite suffix to distinguish from full version
    faiss.write_index(index, "faqs_vector_lite.index")
    with open("faqs_docs_lite.json", "w", encoding="utf-8") as f:
        json.dump(documents, f)
    
    print(f"✅ LITE vector store created with {len(documents)} documents")
    print(f"   Saved as: faqs_vector_lite.index, faqs_docs_lite.json")


if __name__ == "__main__":
    load_to_vector_store()
