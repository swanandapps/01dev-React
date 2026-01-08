"""
Document datastore used by the student-facing AI features (study guides,
questions, quiz sessions, concept performance, knowledge graph, recommendations).

In production it talks to Firestore via the Firebase Admin SDK. Locally — or
anywhere a service-account credential is absent — it falls back to an in-memory
store so the features remain fully testable without Firebase. This mirrors the
graceful-degradation pattern already used by EmbeddingService / AnswerGenerator.

Credential resolution (first hit wins):
  1. FIREBASE_SERVICE_ACCOUNT_JSON  — the service-account JSON as a string (Render-friendly)
  2. GOOGLE_APPLICATION_CREDENTIALS — path to a service-account JSON file
  3. otherwise -> in-memory store (with a loud warning)
"""

import asyncio
import json
import os
from typing import Any, Dict, List, Optional


class InMemoryStore:
    """Dict-of-dicts store. Data is per-process and lost on restart."""

    def __init__(self):
        self._db: Dict[str, Dict[str, dict]] = {}

    def _col(self, collection: str) -> Dict[str, dict]:
        return self._db.setdefault(collection, {})

    async def get(self, collection: str, doc_id: str) -> Optional[dict]:
        return self._col(collection).get(doc_id)

    async def set(self, collection: str, doc_id: str, data: dict) -> None:
        self._col(collection)[doc_id] = {**data}

    async def update(self, collection: str, doc_id: str, changes: dict) -> None:
        doc = self._col(collection).setdefault(doc_id, {})
        doc.update(changes)

    async def query(self, collection: str, field: str, value: Any) -> List[dict]:
        return [d for d in self._col(collection).values() if d.get(field) == value]

    async def list_all(self, collection: str) -> List[dict]:
        return list(self._col(collection).values())

    async def delete(self, collection: str, doc_id: str) -> None:
        self._col(collection).pop(doc_id, None)


class FirestoreStore:
    """Firestore-backed store. Sync Admin SDK calls are run in threads."""

    def __init__(self, client):
        self._client = client

    async def get(self, collection: str, doc_id: str) -> Optional[dict]:
        def _op():
            snap = self._client.collection(collection).document(doc_id).get()
            return snap.to_dict() if snap.exists else None
        return await asyncio.to_thread(_op)

    async def set(self, collection: str, doc_id: str, data: dict) -> None:
        def _op():
            self._client.collection(collection).document(doc_id).set(data)
        await asyncio.to_thread(_op)

    async def update(self, collection: str, doc_id: str, changes: dict) -> None:
        def _op():
            # set(merge=True) so it upserts even if the doc doesn't exist yet.
            self._client.collection(collection).document(doc_id).set(changes, merge=True)
        await asyncio.to_thread(_op)

    async def query(self, collection: str, field: str, value: Any) -> List[dict]:
        def _op():
            docs = self._client.collection(collection).where(field, "==", value).stream()
            return [d.to_dict() for d in docs]
        return await asyncio.to_thread(_op)

    async def list_all(self, collection: str) -> List[dict]:
        def _op():
            return [d.to_dict() for d in self._client.collection(collection).stream()]
        return await asyncio.to_thread(_op)

    async def delete(self, collection: str, doc_id: str) -> None:
        def _op():
            self._client.collection(collection).document(doc_id).delete()
        await asyncio.to_thread(_op)


def _init_store():
    sa_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
    sa_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

    if not sa_json and not sa_path:
        print("Store: no Firebase credentials — using in-memory store (data NOT persisted).")
        return InMemoryStore()

    try:
        import firebase_admin
        from firebase_admin import credentials, firestore

        if not firebase_admin._apps:
            if sa_json:
                cred = credentials.Certificate(json.loads(sa_json))
            else:
                cred = credentials.Certificate(sa_path)
            firebase_admin.initialize_app(cred)

        print("Store: using Firestore (Firebase Admin SDK).")
        return FirestoreStore(firestore.client())
    except Exception as e:  # noqa: BLE001 — never let storage init crash the app
        print(f"Store: Firebase init failed ({e}); falling back to in-memory store.")
        return InMemoryStore()


store = _init_store()
