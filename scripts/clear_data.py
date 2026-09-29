"""Reset script to clear Neo4j graph, Qdrant vectors, and Store Registry."""

import json
from pathlib import Path
from neo4j import GraphDatabase
from qdrant_client import QdrantClient

def clear_neo4j(uri: str = "bolt://localhost:7687", user: str = "neo4j", password: str = "production_password"):
    try:
        driver = GraphDatabase.driver(uri, auth=(user, password))
        with driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")
            count = session.run("MATCH (n) RETURN count(n) AS cnt").single()["cnt"]
        driver.close()
        print(f"[OK] Neo4j cleared. Current node count: {count}")
    except Exception as exc:
        print(f"[WARN] Failed to clear Neo4j: {exc}")

def clear_qdrant(url: str = "http://localhost:6333", collection_name: str = "financial_chunks"):
    try:
        client = QdrantClient(url=url)
        collections = [c.name for c in client.get_collections().collections]
        if collection_name in collections:
            client.delete_collection(collection_name=collection_name)
            print(f"[OK] Qdrant collection '{collection_name}' deleted.")
        else:
            print(f"[INFO] Qdrant collection '{collection_name}' does not exist.")
    except Exception as exc:
        print(f"[WARN] Failed to clear Qdrant: {exc}")

def reset_stores_registry(path: str = "data/stores_registry.json"):
    registry_path = Path(path)
    fresh_state = {
        "stores": [
            {
                "id": "default",
                "name": "Main Ledger",
                "description": "Default financial intelligence store",
                "created_at": "2026-09-29 09:30:00",
                "documents": []
            }
        ],
        "history": {}
    }
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(json.dumps(fresh_state, indent=2), encoding="utf-8")
    print(f"[OK] Store registry reset to fresh default: {path}")

if __name__ == "__main__":
    print("Clearing all data from the system...")
    clear_neo4j()
    clear_qdrant()
    reset_stores_registry()
    print("All data successfully cleared! Ready for fresh input.")
