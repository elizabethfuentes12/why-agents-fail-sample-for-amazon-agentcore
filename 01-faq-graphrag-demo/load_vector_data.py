# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Build the FAISS vector store for Traditional RAG (full dataset).

How this script works
---------------------
1. Reads every hotel FAQ .txt file under data/.
2. Embeds each document locally with SentenceTransformer ('all-MiniLM-L6-v2') —
   no API key or cost, 384-dimension vectors.
3. Builds a FAISS IndexFlatL2 (exact L2 similarity) and writes it to
   faqs_vector.index, with the raw documents saved to faqs_docs.json.

The agent's search_faqs tool later reads this index to do top-k similarity
search. This is the "RAG" side of the Graph-RAG comparison; build_graph.py
builds the Neo4j graph for the "Graph-RAG" side from the SAME documents.
"""
import faiss
import json
from pathlib import Path
from sentence_transformers import SentenceTransformer

def load_to_vector_store():
    model = SentenceTransformer('all-MiniLM-L6-v2')
    
    documents = []
    data_dir = Path("data")
    
    for faq_file in sorted(data_dir.glob("*.txt")):
        with open(faq_file, 'r', encoding='utf-8') as f:
            text = f.read()
            documents.append({
                'filename': faq_file.name,
                'text': text
            })
    
    print(f"Loading {len(documents)} FAQ documents...")
    
    texts = [doc['text'] for doc in documents]
    embeddings = model.encode(texts, show_progress_bar=True)
    
    dimension = embeddings.shape[1]
    index = faiss.IndexFlatL2(dimension)
    index.add(embeddings.astype('float32'))
    
    faiss.write_index(index, "faqs_vector.index")
    with open("faqs_docs.json", "w", encoding="utf-8") as f:
        json.dump(documents, f)
    
    print(f"✅ Vector store created with {len(documents)} documents")

if __name__ == "__main__":
    load_to_vector_store()
