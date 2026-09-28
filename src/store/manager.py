"""Store management and short-term conversation memory scoped by store_id."""

from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any, List, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class DocumentMetadata(BaseModel):
    doc_id: str
    store_id: str
    filename: str
    file_type: str
    uploaded_at: str = Field(default_factory=lambda: time.strftime("%Y-%m-%d %H:%M:%S"))
    total_chunks: int = 0
    chunk_types: List[str] = Field(default_factory=list)


class ChatMessage(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    role: str  # "user" or "assistant"
    content: str
    citations: List[dict[str, Any]] = Field(default_factory=list)
    graph_nodes_traversed: List[str] = Field(default_factory=list)
    route_used: Optional[str] = None
    dashboard_payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: float = Field(default_factory=time.time)


class Store(BaseModel):
    id: str
    name: str
    description: str = ""
    created_at: str = Field(default_factory=lambda: time.strftime("%Y-%m-%d %H:%M:%S"))
    documents: List[DocumentMetadata] = Field(default_factory=list)


class StoreManager:
    """Thread-safe persistent store catalog and per-store short term memory."""

    def __init__(self, persistence_file: str | Path = "data/stores_registry.json"):
        self.file_path = Path(persistence_file)
        self._stores: dict[str, Store] = {}
        self._history: dict[str, list[ChatMessage]] = {}
        self._load()

    def _load(self) -> None:
        try:
            if self.file_path.exists():
                content = self.file_path.read_text(encoding="utf-8")
                if content.strip():
                    data = json.loads(content)
                    for store_data in data.get("stores", []):
                        store = Store.model_validate(store_data)
                        self._stores[store.id] = store
                    for store_id, messages in data.get("history", {}).items():
                        self._history[store_id] = [
                            ChatMessage.model_validate(msg) for msg in messages
                        ]
        except Exception as exc:
            logger.warning("Failed to load store registry: %s. Initializing fresh.", exc)

        if "default" not in self._stores:
            self._stores["default"] = Store(
                id="default",
                name="Main Ledger",
                description="Default financial intelligence store",
            )
            self._save()

    def _save(self) -> None:
        try:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "stores": [store.model_dump() for store in self._stores.values()],
                "history": {
                    sid: [msg.model_dump() for msg in msgs]
                    for sid, msgs in self._history.items()
                },
            }
            self.file_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.error("Failed to save store registry: %s", exc)

    def list_stores(self) -> list[Store]:
        return list(self._stores.values())

    def get_store(self, store_id: str) -> Optional[Store]:
        return self._stores.get(store_id)

    def create_store(self, name: str, description: str = "") -> Store:
        store_id = str(uuid.uuid4())[:8]
        clean_name = name.strip() or f"Store {store_id}"
        store = Store(id=store_id, name=clean_name, description=description.strip())
        self._stores[store_id] = store
        self._history[store_id] = []
        self._save()
        logger.info("Store created id=%s name=%s", store_id, clean_name)
        return store

    def delete_store(self, store_id: str) -> bool:
        if store_id == "default":
            # Don't delete default store, just clear its documents and history
            if "default" in self._stores:
                self._stores["default"].documents = []
                self._history["default"] = []
                self._save()
            return True
        if store_id in self._stores:
            del self._stores[store_id]
            self._history.pop(store_id, None)
            self._save()
            return True
        return False

    def add_document(self, store_id: str, doc: DocumentMetadata) -> DocumentMetadata:
        store = self.get_store(store_id)
        if not store:
            store = self.create_store(name=f"Store {store_id}")
            store.id = store_id
            self._stores[store_id] = store
        # Remove existing if same doc_id or same filename
        store.documents = [d for d in store.documents if d.doc_id != doc.doc_id and d.filename != doc.filename]
        store.documents.append(doc)
        self._save()
        return doc

    def list_documents(self, store_id: str) -> list[DocumentMetadata]:
        store = self.get_store(store_id)
        return list(store.documents) if store else []

    def get_chat_history(self, store_id: str, limit: int = 50) -> list[ChatMessage]:
        messages = self._history.get(store_id, [])
        return messages[-limit:]

    def add_message(
        self,
        store_id: str,
        role: str,
        content: str,
        citations: list[dict[str, Any]] | None = None,
        graph_nodes_traversed: list[str] | None = None,
        route_used: str | None = None,
        dashboard_payload: dict[str, Any] | None = None,
    ) -> ChatMessage:
        msg = ChatMessage(
            role=role,
            content=content,
            citations=citations or [],
            graph_nodes_traversed=graph_nodes_traversed or [],
            route_used=route_used,
            dashboard_payload=dashboard_payload or {},
            timestamp=time.time(),
        )
        if store_id not in self._history:
            self._history[store_id] = []
        self._history[store_id].append(msg)
        # Cap store history to 100 messages to prevent unbounded growth
        if len(self._history[store_id]) > 100:
            self._history[store_id] = self._history[store_id][-100:]
        self._save()
        return msg

    def clear_chat_history(self, store_id: str) -> bool:
        if store_id in self._history:
            self._history[store_id] = []
            self._save()
            return True
        return False

    def format_short_term_memory(self, store_id: str, max_turns: int = 6) -> str:
        """Format recent conversation history as short-term memory context for the LLM."""
        history = self.get_chat_history(store_id, limit=max_turns * 2)
        if not history:
            return ""
        lines = ["Recent Conversation History:"]
        for msg in history[-max_turns * 2:]:
            speaker = "User" if msg.role == "user" else "Assistant"
            clean_content = msg.content.strip().replace("\n", " ")
            if len(clean_content) > 300:
                clean_content = clean_content[:300] + "..."
            lines.append(f"{speaker}: {clean_content}")
        return "\n".join(lines)
