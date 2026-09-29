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
