"""SQLite vector-light RAG: hashing-trick embeddings stored next to the catalog.

No extra packages. Each product/review/memory row keeps a unit vector in
`rag_docs`; retrieval is cosine similarity in Python. Kernel still decides money.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterable

from ..models import Product, now_utc

if TYPE_CHECKING:
    from .db import Database

EMBED_DIM = 64
TOKEN_RE = re.compile(r"[a-z0-9]+")
STOP = {
    "a", "an", "and", "for", "in", "of", "on", "or", "the", "to", "with",
    "this", "that", "from", "by", "is", "are", "it",
}


def _tokens(text: str) -> list[str]:
    words = [w for w in TOKEN_RE.findall(text.lower()) if w not in STOP and len(w) > 1]
    grams = list(words)
    grams.extend(f"{left}_{right}" for left, right in zip(words, words[1:]))
    return grams


def embed_text(text: str, *, dim: int = EMBED_DIM) -> list[float]:
    """Deterministic hashing-trick embedding (signed bag of n-grams)."""
    vec = [0.0] * dim
    for token in _tokens(text):
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        idx = int.from_bytes(digest[:4], "little") % dim
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0:
        return vec
    return [v / norm for v in vec]


def cosine(left: list[float], right: list[float]) -> float:
    n = min(len(left), len(right))
    if n == 0:
        return 0.0
    return sum(left[i] * right[i] for i in range(n))


def product_blob(product: Product) -> str:
    attrs = product.attributes or {}
    attr_bits = " ".join(f"{key}={value}" for key, value in sorted(attrs.items()))
    return f"{product.title} {product.description} {attr_bits}"


def review_blob(*, body: str, rating: int, product_id: str) -> str:
    return f"review product={product_id} rating={rating} {body}"


@dataclass(frozen=True)
class RagHit:
    doc_id: str
    kind: str
    ref_id: str
    seller_id: str | None
    text: str
    score: float


def _upsert_doc(
    conn: sqlite3.Connection,
    *,
    doc_id: str,
    kind: str,
    ref_id: str,
    seller_id: str | None,
    text: str,
    embedding: list[float],
) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO rag_docs(id,kind,ref_id,seller_id,text,embedding_json,created_at) VALUES(?,?,?,?,?,?,?)",
        (doc_id, kind, ref_id, seller_id, text, json.dumps(embedding), now_utc().isoformat()),
    )


def index_product(conn: sqlite3.Connection, product: Product) -> None:
    blob = product_blob(product)
    embedding = product.embedding or embed_text(blob)
    _upsert_doc(
        conn,
        doc_id=f"product:{product.id}",
        kind="product",
        ref_id=product.id,
        seller_id=product.seller_id,
        text=blob,
        embedding=embedding,
    )


def index_review(
    conn: sqlite3.Connection,
    *,
    review_id: str,
    product_id: str,
    seller_id: str | None,
    body: str,
    rating: int,
) -> None:
    blob = review_blob(body=body, rating=rating, product_id=product_id)
    _upsert_doc(
        conn,
        doc_id=f"review:{review_id}",
        kind="review",
        ref_id=review_id,
        seller_id=seller_id,
        text=blob,
        embedding=embed_text(blob),
    )


def index_memory(conn: sqlite3.Connection, *, session_id: str, seq: int, text: str, seller_id: str | None = None) -> None:
    blob = text.strip()
    if not blob:
        return
    _upsert_doc(
        conn,
        doc_id=f"memory:{session_id}:{seq}",
        kind="memory",
        ref_id=session_id,
        seller_id=seller_id,
        text=blob,
        embedding=embed_text(blob),
    )


class CatalogRag:
    """Retrieve catalog / review / session-memory snippets for advisory prompts."""

    def __init__(self, db: Database):
        self.db = db

    def retrieve(
        self,
        query: str,
        *,
        k: int = 4,
        seller_id: str | None = None,
        kinds: Iterable[str] | None = None,
        session_id: str | None = None,
    ) -> list[RagHit]:
        query_vec = embed_text(query)
        allowed = set(kinds) if kinds is not None else None
        sql = "SELECT id, kind, ref_id, seller_id, text, embedding_json FROM rag_docs"
        params: list[object] = []
        clauses: list[str] = []
        if seller_id:
            clauses.append("(seller_id = ? OR seller_id IS NULL)")
            params.append(seller_id)
        if session_id:
            clauses.append("(kind != 'memory' OR ref_id = ?)")
            params.append(session_id)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        hits: list[RagHit] = []
        for row in self.db.conn.execute(sql, params):
            kind = row["kind"]
            if allowed is not None and kind not in allowed:
                continue
            embedding = json.loads(row["embedding_json"])
            score = cosine(query_vec, embedding)
            hits.append(
                RagHit(
                    doc_id=row["id"],
                    kind=kind,
                    ref_id=row["ref_id"],
                    seller_id=row["seller_id"],
                    text=row["text"],
                    score=score,
                )
            )
        hits.sort(key=lambda hit: hit.score, reverse=True)
        return [hit for hit in hits if hit.score > 0][:k]

    def rank_products(self, query: str, products: list[Product]) -> list[Product]:
        if not products:
            return []
        query_vec = embed_text(query)

        def score(product: Product) -> float:
            vec = product.embedding or embed_text(product_blob(product))
            return cosine(query_vec, vec)

        return sorted(products, key=lambda product: (-score(product), product.id))

    def remember(self, *, session_id: str, seq: int, text: str, seller_id: str | None = None) -> None:
        index_memory(self.db.conn, session_id=session_id, seq=seq, text=text, seller_id=seller_id)


def format_hits(hits: list[RagHit], *, limit: int = 4, max_chars: int = 180) -> str:
    if not hits:
        return "(none)"
    lines: list[str] = []
    for hit in hits[:limit]:
        snippet = " ".join(hit.text.split())
        if len(snippet) > max_chars:
            snippet = snippet[: max_chars - 1] + "…"
        lines.append(f"- [{hit.kind} {hit.ref_id} score={hit.score:.2f}] {snippet}")
    return "\n".join(lines)
