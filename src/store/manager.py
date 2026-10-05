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
        self._deleted_store_ids: set[str] = set()
        self._last_mtime: float = 0.0
        self._load()

    def _load_if_needed(self) -> None:
        """Reload from disk if another process or replica updated the file."""
        try:
            if self.file_path.exists():
                mtime = self.file_path.stat().st_mtime
                if mtime > self._last_mtime:
                    self._load()
        except Exception:
            pass

    def _load(self) -> None:
        try:
            if self.file_path.exists():
                content = self.file_path.read_text(encoding="utf-8")
                if content.strip():
                    data = json.loads(content)
                    loaded_stores: dict[str, Store] = {}
                    for store_data in data.get("stores", []):
                        store = Store.model_validate(store_data)
                        if store.id in self._deleted_store_ids:
                            continue
                        if store.id in loaded_stores:
                            existing = loaded_stores[store.id]
                            if existing.name.startswith("Store ") and not store.name.startswith("Store "):
                                existing.name = store.name
                            existing_doc_ids = {d.doc_id for d in existing.documents}
                            for doc in store.documents:
                                if doc.doc_id not in existing_doc_ids:
                                    existing.documents.append(doc)
                                    existing_doc_ids.add(doc.doc_id)
                        else:
                            loaded_stores[store.id] = store

                    # Merge with existing in-memory stores so local changes are preserved
                    for sid, store in self._stores.items():
                        if sid in self._deleted_store_ids:
                            continue
                        if sid not in loaded_stores:
                            loaded_stores[sid] = store
                        else:
                            existing = loaded_stores[sid]
                            if existing.name.startswith("Store ") and not store.name.startswith("Store "):
                                existing.name = store.name
                            existing_doc_ids = {d.doc_id for d in existing.documents}
                            for doc in store.documents:
                                if doc.doc_id not in existing_doc_ids:
                                    existing.documents.append(doc)
                                    existing_doc_ids.add(doc.doc_id)
                    self._stores = loaded_stores

                    for store_id, messages in data.get("history", {}).items():
                        if store_id not in self._history:
                            self._history[store_id] = [
                                ChatMessage.model_validate(msg) for msg in messages
                            ]
                self._last_mtime = self.file_path.stat().st_mtime
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

            # Re-read disk content and merge before writing so another pod's updates are never erased
            if self.file_path.exists():
                try:
                    content = self.file_path.read_text(encoding="utf-8")
                    if content.strip():
                        disk_data = json.loads(content)
                        for s_data in disk_data.get("stores", []):
                            d_store = Store.model_validate(s_data)
                            if d_store.id in self._deleted_store_ids:
                                continue
                            if d_store.id not in self._stores:
                                self._stores[d_store.id] = d_store
                            else:
                                local_store = self._stores[d_store.id]
                                if local_store.name.startswith("Store ") and not d_store.name.startswith("Store "):
                                    local_store.name = d_store.name
                                local_doc_ids = {d.doc_id for d in local_store.documents}
                                for doc in d_store.documents:
                                    if doc.doc_id not in local_doc_ids:
                                        local_store.documents.append(doc)
                                        local_doc_ids.add(doc.doc_id)
                        for sid, msgs in disk_data.get("history", {}).items():
                            if sid not in self._history:
                                self._history[sid] = [ChatMessage.model_validate(m) for m in msgs]
                except Exception as merge_exc:
                    logger.warning("Could not merge disk state before save: %s", merge_exc)

            # Ensure unique stores by ID and exclude deleted stores
            unique_stores: dict[str, Store] = {}
            for sid, store in self._stores.items():
                if sid not in self._deleted_store_ids:
                    unique_stores[store.id] = store
            self._stores = unique_stores

            payload = {
                "stores": [store.model_dump() for store in self._stores.values()],
                "history": {
                    sid: [msg.model_dump() for msg in msgs]
                    for sid, msgs in self._history.items()
                    if sid not in self._deleted_store_ids
                },
            }
            temp_file = self.file_path.with_suffix(".tmp")
            temp_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            temp_file.replace(self.file_path)
            self._last_mtime = self.file_path.stat().st_mtime
        except Exception as exc:
            logger.error("Failed to save store registry: %s", exc)

    def list_stores(self) -> list[Store]:
        self._load_if_needed()
        return list(self._stores.values())

    def get_store(self, store_id: str) -> Optional[Store]:
        self._load_if_needed()
        return self._stores.get(store_id)

    def create_store(self, name: str, description: str = "", store_id: str | None = None) -> Store:
        self._load_if_needed()
        actual_id = store_id or str(uuid.uuid4())[:8]
        self._deleted_store_ids.discard(actual_id)
        clean_name = name.strip() or f"Store {actual_id}"
        store = Store(id=actual_id, name=clean_name, description=description.strip())
        self._stores[actual_id] = store
        if actual_id not in self._history:
            self._history[actual_id] = []
        self._save()
        logger.info("Store created id=%s name=%s", actual_id, clean_name)
        return store

    def delete_store(self, store_id: str) -> bool:
        self._load_if_needed()
        if store_id == "default":
            # Don't delete default store, just clear its documents and history
            if "default" in self._stores:
                self._stores["default"].documents = []
                self._history["default"] = []
                self._save()
            return True
        if store_id in self._stores:
            self._deleted_store_ids.add(store_id)
            del self._stores[store_id]
            self._history.pop(store_id, None)
            self._save()
            return True
        return False

    def add_document(self, store_id: str, doc: DocumentMetadata) -> DocumentMetadata:
        self._load_if_needed()
        store = self.get_store(store_id)
        if not store:
            store = self.create_store(name=f"Store {store_id}", store_id=store_id)
        # Remove existing if same doc_id or same filename
        store.documents = [d for d in store.documents if d.doc_id != doc.doc_id and d.filename != doc.filename]
        store.documents.append(doc)
        self._save()
        return doc

    def list_documents(self, store_id: str) -> list[DocumentMetadata]:
        self._load_if_needed()
        store = self.get_store(store_id)
        return list(store.documents) if store else []

    def sync_documents_from_graph(self, documents: list[dict[str, Any]]) -> int:
        """Reconcile documents discovered from Neo4j into local store state."""
        self._load_if_needed()
        added_count = 0
        for doc_data in documents:
            sid = doc_data.get("store_id") or "default"
            doc_id = doc_data.get("doc_id") or doc_data.get("id")
            filename = doc_data.get("filename")
            if not sid or not doc_id or not filename:
                continue

            store = self._stores.get(sid)
            if not store:
                store_name = doc_data.get("store_name") or f"Store {sid}"
                store = self.create_store(name=store_name, store_id=sid)

            existing_doc_ids = {d.doc_id for d in store.documents}
            if doc_id not in existing_doc_ids:
                doc = DocumentMetadata(
                    doc_id=doc_id,
                    store_id=sid,
                    filename=filename,
                    file_type=doc_data.get("file_type") or Path(filename).suffix or ".txt",
                    uploaded_at=doc_data.get("uploaded_at") or time.strftime("%Y-%m-%d %H:%M:%S"),
                    total_chunks=int(doc_data.get("total_chunks") or 0),
                    chunk_types=doc_data.get("chunk_types") or [],
                )
                store.documents.append(doc)
                added_count += 1

        if added_count > 0:
            self._save()
        return added_count

    def get_chat_history(self, store_id: str, limit: int = 50) -> list[ChatMessage]:
        self._load_if_needed()
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
        self._load_if_needed()
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
        self._load_if_needed()
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
