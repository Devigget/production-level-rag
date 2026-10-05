from fastapi.testclient import TestClient
import pytest
from src.api.server import app, store_manager

client = TestClient(app)


def test_store_creation_and_listing():
    create_res = client.post(
        "/api/stores",
        json={"name": "North America Retail", "description": "Retail branch financials"},
    )
    assert create_res.status_code == 200
    store = create_res.json()
    assert store["name"] == "North America Retail"
    assert store["id"] is not None

    list_res = client.get("/api/stores")
    assert list_res.status_code == 200
    stores = list_res.json()
    assert any(s["id"] == store["id"] for s in stores)


def test_store_scoped_upload_and_document_tracking():
    # 1. Create a dedicated store
    store_res = client.post("/api/stores", json={"name": "EMEA Operations"}).json()
    store_id = store_res["id"]

    # 2. Upload CSV into that store
    csv_bytes = b"Item,Q1,Q2\nLaptops,50000,75000\nPhones,30000,45000\n"
    upload_res = client.post(
        "/api/upload",
        files={"file": ("sales.csv", csv_bytes, "text/csv")},
        data={"store_id": store_id},
    )
    assert upload_res.status_code == 200
    payload = upload_res.json()
    assert payload["store_id"] == store_id
    assert payload["total_chunks"] == 2

    # 3. Retrieve documents for that store
    docs_res = client.get(f"/api/stores/{store_id}/documents")
    assert docs_res.status_code == 200
    docs = docs_res.json()
    assert len(docs) == 1
    assert docs[0]["filename"] == "sales.csv"
    assert docs[0]["store_id"] == store_id


def test_store_short_term_memory_persistence():
    store_res = client.post("/api/stores", json={"name": "APAC Logistics"}).json()
    store_id = store_res["id"]

    # Simulate message recording
    store_manager.add_message(store_id, "user", "What was Q1 revenue?")
    store_manager.add_message(store_id, "assistant", "Q1 revenue was $50,000.", route_used="HYBRID")

    # Fetch messages via API
    msg_res = client.get(f"/api/stores/{store_id}/messages")
    assert msg_res.status_code == 200
    messages = msg_res.json()
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "What was Q1 revenue?"
    assert messages[1]["role"] == "assistant"
    assert messages[1]["content"] == "Q1 revenue was $50,000."

    # Format short term memory
    formatted = store_manager.format_short_term_memory(store_id)
    assert "User: What was Q1 revenue?" in formatted
    assert "Assistant: Q1 revenue was $50,000." in formatted

    # Clear chat
    clear_res = client.post(f"/api/stores/{store_id}/clear-chat")
    assert clear_res.status_code == 200
    msg_res_after = client.get(f"/api/stores/{store_id}/messages")
    assert len(msg_res_after.json()) == 0


def test_query_router_classification():
    from src.retrieval.router import QueryRouter, ROUTE_GRAPH, ROUTE_HYBRID, ROUTE_VECTOR

    router = QueryRouter()

    route, _ = router.route_query("Explain the accounting policy on depreciation.")
    assert route == ROUTE_VECTOR

    route, _ = router.route_query("What is the difference and growth between Q1 and Q2 revenue?")
    assert route == ROUTE_GRAPH

    route, _ = router.route_query("What is the total revenue in Q1 and why did margins change?")
    assert route == ROUTE_HYBRID

    route, _ = router.route_query("What was the strongest quarter?")
    assert route == ROUTE_GRAPH

    cypher, params = router.generate_store_cypher("What was the strongest quarter?", "store_123")
    assert "ORDER BY coalesce(r.numeric_value, 0) DESC" in cypher


def test_store_manager_cross_replica_sync_and_deduplication(tmp_path):
    from src.store.manager import StoreManager, DocumentMetadata

    registry_file = tmp_path / "stores_registry.json"
    replica_1 = StoreManager(persistence_file=registry_file)
    replica_2 = StoreManager(persistence_file=registry_file)

    # 1. Replica 1 creates store
    store = replica_1.create_store(name="Brew and Bean")
    assert store.name == "Brew and Bean"

    # 2. Replica 2 immediately sees it on list_stores without manual restart
    stores_on_r2 = replica_2.list_stores()
    assert any(s.id == store.id and s.name == "Brew and Bean" for s in stores_on_r2)

    # 3. Replica 2 adds document
    doc = DocumentMetadata(doc_id="doc1", store_id=store.id, filename="q4.pdf", file_type=".pdf")
    replica_2.add_document(store.id, doc)

    # 4. Replica 1 immediately sees the document
    docs_on_r1 = replica_1.list_documents(store.id)
    assert len(docs_on_r1) == 1
    assert docs_on_r1[0].doc_id == "doc1"

    # 5. Test chat message on Replica 2 does NOT erase Replica 1's newly added documents
    doc2 = DocumentMetadata(doc_id="doc2", store_id=store.id, filename="invoice.png", file_type=".png")
    replica_1.add_document(store.id, doc2)

    # Replica 2 handles a chat message (which calls add_message and saves)
    replica_2.add_message(store.id, role="user", content="Hello")

    # Verify both replicas still see both documents
    docs_r1_after = replica_1.list_documents(store.id)
    docs_r2_after = replica_2.list_documents(store.id)
    assert len(docs_r1_after) == 2
    assert len(docs_r2_after) == 2
    filenames_r2 = {d.filename for d in docs_r2_after}
    assert "invoice.png" in filenames_r2
    assert "q4.pdf" in filenames_r2

    # 6. Verify no duplicate IDs exist
    all_ids = [s.id for s in replica_1.list_stores()]
    assert len(all_ids) == len(set(all_ids))


def test_store_manager_sync_from_graph(tmp_path):
    from src.store.manager import StoreManager

    registry_file = tmp_path / "stores_registry.json"
    manager = StoreManager(persistence_file=registry_file)

    graph_docs = [
        {
            "store_id": "store-xyz",
            "store_name": "Coffee Roasters",
            "doc_id": "doc-graph-1",
            "filename": "beans_invoice.png",
            "file_type": ".png",
            "total_chunks": 1,
            "chunk_types": ["image_ocr"],
            "uploaded_at": "2026-10-05 10:00:00",
        }
    ]

    added = manager.sync_documents_from_graph(graph_docs)
    assert added == 1

    docs = manager.list_documents("store-xyz")
    assert len(docs) == 1
    assert docs[0].filename == "beans_invoice.png"
    assert docs[0].file_type == ".png"

    # Idempotent call doesn't duplicate
    added_again = manager.sync_documents_from_graph(graph_docs)
    assert added_again == 0
    assert len(manager.list_documents("store-xyz")) == 1
