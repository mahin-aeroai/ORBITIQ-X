"""
ORBITIQ-X — Upload Phase 19 Corpus to Qdrant
=============================================
Uploads the v0.5 corpus expansion chunks to Qdrant.
Combines with existing v0.4 corpus for 185 + 67 = 252 chunks total.
Run from Railway shell or locally with QDRANT_URL + QDRANT_API_KEY env vars.

Usage:
  python scripts/upload_corpus_v05.py

Environment variables required:
  QDRANT_URL      — Qdrant cluster URL
  QDRANT_API_KEY  — Qdrant API key
  ANTHROPIC_API_KEY — For embeddings via Claude (or use local model)
"""
import os, json, sys

def main():
    try:
        from qdrant_client import QdrantClient
        from qdrant_client.models import PointStruct, VectorParams, Distance
    except ImportError:
        print("Install: pip install qdrant-client")
        sys.exit(1)

    qdrant_url = os.environ.get("QDRANT_URL", "")
    qdrant_key = os.environ.get("QDRANT_API_KEY", "")

    if not qdrant_url:
        print("Set QDRANT_URL environment variable")
        sys.exit(1)

    client = QdrantClient(url=qdrant_url, api_key=qdrant_key)
    collection = "aerospace_docs"

    # Load v0.5 corpus
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from corpus_seed_v05 import CORPUS_V5

    print(f"Uploading {len(CORPUS_V5)} chunks to {collection}...")

    # Use a simple embedding function (replace with actual embedding call)
    def embed(text: str) -> list:
        """Replace with actual embedding API call."""
        # Placeholder: random 384-dim vector
        import random
        return [random.gauss(0, 0.1) for _ in range(384)]

    points = []
    for i, chunk in enumerate(CORPUS_V5):
        vector = embed(chunk["text"])
        points.append(PointStruct(
            id=abs(hash(chunk["id"])) % (2**31),
            vector=vector,
            payload={
                "chunk_id":     chunk["id"],
                "domain":       chunk["domain"],
                "title":        chunk["title"],
                "source":       chunk["source"],
                "text":         chunk["text"],
                "corpus_version": "v0.5",
            }
        ))
        if (i + 1) % 10 == 0:
            print(f"  Prepared {i+1}/{len(CORPUS_V5)} chunks...")

    # Upload in batches
    batch_size = 20
    for i in range(0, len(points), batch_size):
        batch = points[i:i+batch_size]
        client.upsert(collection_name=collection, points=batch)
        print(f"  Uploaded batch {i//batch_size + 1}/{len(points)//batch_size + 1}")

    # Verify
    info = client.get_collection(collection)
    print(f"\nCollection '{collection}': {info.points_count} total points")
    print("Upload complete")

if __name__ == "__main__":
    main()
