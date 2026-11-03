"""In-memory book store.

This keeps the example dependency-free. A real service must use a database
(DynamoDB, Firestore, Cosmos DB, PostgreSQL, ...): serverless instances are
created and destroyed at any time and do NOT share memory, so data stored here
lives only as long as one warm instance.
"""

from __future__ import annotations

import threading
import uuid
from typing import Dict, List, Optional

_LOCK = threading.Lock()
_BOOKS: Dict[str, dict] = {
    "b1": {"id": "b1", "title": "Dune", "author": "Frank Herbert", "year": 1965, "isbn": "9780441013593"},
    "b2": {"id": "b2", "title": "Neuromancer", "author": "William Gibson", "year": 1984, "isbn": "9780441569595"},
}


def list_books(author: Optional[str] = None) -> List[dict]:
    with _LOCK:
        books = list(_BOOKS.values())
    if author:
        books = [b for b in books if author.lower() in b["author"].lower()]
    return sorted(books, key=lambda b: b["title"])


def get(book_id: str) -> Optional[dict]:
    with _LOCK:
        return _BOOKS.get(book_id)


def find_by_isbn(isbn: str) -> Optional[dict]:
    with _LOCK:
        return next((b for b in _BOOKS.values() if b["isbn"] == isbn), None)


def put(book: dict) -> dict:
    with _LOCK:
        book = dict(book)
        book.setdefault("id", uuid.uuid4().hex[:8])
        _BOOKS[book["id"]] = book
        return book


def delete(book_id: str) -> bool:
    with _LOCK:
        return _BOOKS.pop(book_id, None) is not None
