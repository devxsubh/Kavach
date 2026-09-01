from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from ..exceptions import ReplayError
from ..models import AuditEvent, Buyer, Order, Product, Seller, now_utc
from ..signing import canonical_bytes, digest


SCHEMA = """
CREATE TABLE IF NOT EXISTS sellers (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, policy_profile TEXT NOT NULL,
 price_floor_pct REAL NOT NULL, reputation_seed REAL NOT NULL, pubkey TEXT NOT NULL,
 is_adversarial INTEGER NOT NULL, attack_class TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS products (
 id TEXT PRIMARY KEY, seller_id TEXT NOT NULL, title TEXT NOT NULL, description TEXT NOT NULL,
 list_price_minor INTEGER NOT NULL, stock INTEGER NOT NULL, attributes_json TEXT NOT NULL,
 embedding_json TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS buyers (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, wallet_balance_minor INTEGER NOT NULL,
 pubkey TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reviews (
 id TEXT PRIMARY KEY, product_id TEXT NOT NULL, author_id TEXT NOT NULL, rating INTEGER NOT NULL,
 body TEXT NOT NULL, is_synthetic INTEGER NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS escalations (
 request_id TEXT PRIMARY KEY, buyer_id TEXT NOT NULL, seller_id TEXT NOT NULL, amount_minor INTEGER NOT NULL,
 reason TEXT NOT NULL, expires_at TEXT NOT NULL, status TEXT NOT NULL, approval_ref TEXT
);
CREATE TABLE IF NOT EXISTS orders (
 id TEXT PRIMARY KEY, buyer_id TEXT NOT NULL, seller_id TEXT NOT NULL, product_id TEXT NOT NULL,
 unit_price_minor INTEGER NOT NULL, qty INTEGER NOT NULL, cart_mandate_id TEXT NOT NULL,
 payment_mandate_id TEXT, state TEXT NOT NULL, idempotency_key TEXT UNIQUE NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ledger (
 id INTEGER PRIMARY KEY AUTOINCREMENT, buyer_id TEXT NOT NULL, delta INTEGER NOT NULL,
 reason TEXT NOT NULL, order_id TEXT, balance_after INTEGER NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS holds (
 id INTEGER PRIMARY KEY AUTOINCREMENT, buyer_id TEXT NOT NULL, order_id TEXT UNIQUE NOT NULL,
 amount_minor INTEGER NOT NULL, state TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS payment_refs (
 order_id TEXT PRIMARY KEY, provider TEXT NOT NULL, external_id TEXT NOT NULL UNIQUE,
 status TEXT NOT NULL, amount_minor INTEGER NOT NULL, currency TEXT NOT NULL,
 payment_id TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_log (
 seq INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, actor TEXT NOT NULL,
 event_type TEXT NOT NULL, payload_json TEXT NOT NULL, prev_hash TEXT NOT NULL, hash TEXT NOT NULL
);
"""


class Database:
    def __init__(self, path: str | Path = ":memory:"):
        self.path = str(path)
        self.conn = sqlite3.connect(self.path, isolation_level=None, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)
        self.verify_audit_chain()

    def close(self) -> None:
        self.conn.close()

    def add_seller(self, seller: Seller) -> None:
        self.conn.execute("INSERT OR REPLACE INTO sellers VALUES (?,?,?,?,?,?,?,?,?)", (
            seller.id, seller.name, seller.policy_profile, seller.price_floor_pct,
            seller.reputation_seed, seller.pubkey, int(seller.is_adversarial), seller.attack_class, now_utc().isoformat()))

    def add_product(self, product: Product) -> None:
        self.conn.execute("INSERT OR REPLACE INTO products VALUES (?,?,?,?,?,?,?,?,?)", (
            product.id, product.seller_id, product.title, product.description, product.list_price_minor,
            product.stock, json.dumps(product.attributes, sort_keys=True),
            json.dumps(product.embedding) if product.embedding is not None else None, now_utc().isoformat()))

    def add_buyer(self, buyer: Buyer) -> None:
        self.conn.execute("INSERT OR REPLACE INTO buyers VALUES (?,?,?,?,?)", (
            buyer.id, buyer.name, buyer.wallet_balance_minor, buyer.pubkey, now_utc().isoformat()))

    def add_review(self, review: Any) -> None:
        self.conn.execute("INSERT OR REPLACE INTO reviews VALUES (?,?,?,?,?,?,?)", (review.id, review.product_id, review.author_id, review.rating, review.body, int(review.is_synthetic), review.created_at.isoformat()))

    def list_reviews(self, product_id: str) -> list[Any]:
        from ..advanced_models import Review
        rows = self.conn.execute("SELECT * FROM reviews WHERE product_id=? ORDER BY created_at", (product_id,)).fetchall()
        return [Review(id=r["id"], product_id=r["product_id"], author_id=r["author_id"], rating=r["rating"], body=r["body"], is_synthetic=bool(r["is_synthetic"]), created_at=r["created_at"]) for r in rows]

    def save_escalation(self, request: Any) -> None:
        self.conn.execute("INSERT OR REPLACE INTO escalations VALUES (?,?,?,?,?,?,?,?)", (request.request_id, request.buyer_id, request.seller_id, request.amount_minor, request.reason, request.expires_at.isoformat(), request.status.value, request.approval_ref))

    def get_buyer(self, buyer_id: str) -> Buyer:
        row = self.conn.execute("SELECT * FROM buyers WHERE id=?", (buyer_id,)).fetchone()
        if not row:
            raise KeyError(buyer_id)
        return Buyer(id=row["id"], name=row["name"], wallet_balance_minor=row["wallet_balance_minor"], pubkey=row["pubkey"])

    def get_seller(self, seller_id: str) -> Seller:
        row = self.conn.execute("SELECT * FROM sellers WHERE id=?", (seller_id,)).fetchone()
        if not row:
            raise KeyError(seller_id)
        return Seller(id=row["id"], name=row["name"], policy_profile=row["policy_profile"], price_floor_pct=row["price_floor_pct"], reputation_seed=row["reputation_seed"], pubkey=row["pubkey"], is_adversarial=bool(row["is_adversarial"]), attack_class=row["attack_class"])

    def get_product(self, product_id: str) -> Product:
        row = self.conn.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
        if not row:
            raise KeyError(product_id)
        return Product(id=row["id"], seller_id=row["seller_id"], title=row["title"], description=row["description"], list_price_minor=row["list_price_minor"], stock=row["stock"], attributes=json.loads(row["attributes_json"]), embedding=json.loads(row["embedding_json"]) if row["embedding_json"] else None)

    def search_products(self, category: str | None = None) -> list[Product]:
        rows = self.conn.execute("SELECT id FROM products ORDER BY id").fetchall()
        products = [self.get_product(row["id"]) for row in rows]
        if category:
            products = [p for p in products if p.attributes.get("category") == category]
        return products

    def insert_order(self, order: Order) -> None:
        self.conn.execute("INSERT INTO orders VALUES (?,?,?,?,?,?,?,?,?,?,?)", (
            order.id, order.buyer_id, order.seller_id, order.product_id, order.unit_price_minor,
            order.qty, order.cart_mandate_id, order.payment_mandate_id, order.state.value,
            order.idempotency_key, order.created_at.isoformat()))

    def get_order(self, order_id: str) -> Order:
        row = self.conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
        if not row:
            raise KeyError(order_id)
        return Order(id=row["id"], buyer_id=row["buyer_id"], seller_id=row["seller_id"], product_id=row["product_id"], unit_price_minor=row["unit_price_minor"], qty=row["qty"], cart_mandate_id=row["cart_mandate_id"], payment_mandate_id=row["payment_mandate_id"], state=row["state"], idempotency_key=row["idempotency_key"], created_at=row["created_at"])

    def update_order(self, order: Order) -> None:
        self.conn.execute("UPDATE orders SET payment_mandate_id=?, state=? WHERE id=?", (order.payment_mandate_id, order.state.value, order.id))

    def update_stock(self, product_id: str, qty_delta: int) -> None:
        self.conn.execute("UPDATE products SET stock=stock+? WHERE id=?", (qty_delta, product_id))

    def _apply_delta(self, buyer_id: str, delta: int, reason: str, order_id: str | None) -> int:
        row = self.conn.execute("SELECT wallet_balance_minor FROM buyers WHERE id=?", (buyer_id,)).fetchone()
        if not row:
            raise KeyError(buyer_id)
        balance = row[0] + delta
        if balance < 0:
            raise ValueError("wallet cannot go negative")
        self.conn.execute("UPDATE buyers SET wallet_balance_minor=? WHERE id=?", (balance, buyer_id))
        self.conn.execute("INSERT INTO ledger(buyer_id,delta,reason,order_id,balance_after,created_at) VALUES(?,?,?,?,?,?)", (buyer_id, delta, reason, order_id, balance, now_utc().isoformat()))
        return balance

    def debit(self, buyer_id: str, delta: int, reason: str, order_id: str | None = None) -> int:
        return self._apply_delta(buyer_id, delta, reason, order_id)

    def held_total(self, buyer_id: str) -> int:
        row = self.conn.execute("SELECT COALESCE(SUM(amount_minor), 0) FROM holds WHERE buyer_id=? AND state='HELD'", (buyer_id,)).fetchone()
        return int(row[0])

    def available_balance(self, buyer_id: str) -> int:
        return self.get_buyer(buyer_id).wallet_balance_minor - self.held_total(buyer_id)

    def place_hold(self, buyer_id: str, order_id: str, amount_minor: int) -> int:
        """Reserve funds atomically so the balance check and the claim cannot interleave.

        The UNIQUE constraint on order_id makes a repeated hold for the same order fail
        instead of double-reserving.
        """
        if amount_minor <= 0:
            raise ValueError("hold amount must be positive")
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            row = self.conn.execute("SELECT wallet_balance_minor FROM buyers WHERE id=?", (buyer_id,)).fetchone()
            if not row:
                raise KeyError(buyer_id)
            held = self.conn.execute("SELECT COALESCE(SUM(amount_minor), 0) FROM holds WHERE buyer_id=? AND state='HELD'", (buyer_id,)).fetchone()[0]
            available = row[0] - int(held)
            if available < amount_minor:
                raise ValueError("insufficient available balance")
            self.conn.execute(
                "INSERT INTO holds(buyer_id,order_id,amount_minor,state,created_at) VALUES(?,?,?,'HELD',?)",
                (buyer_id, order_id, amount_minor, now_utc().isoformat()),
            )
        except Exception:
            self.conn.execute("ROLLBACK")
            raise
        self.conn.execute("COMMIT")
        return available - amount_minor

    def settle_hold(self, order_id: str, reason: str = "order authorization") -> int:
        """Convert a held amount into a real debit exactly once."""
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            row = self.conn.execute("SELECT buyer_id, amount_minor, state FROM holds WHERE order_id=?", (order_id,)).fetchone()
            if not row:
                raise KeyError(order_id)
            if row["state"] != "HELD":
                balance = self.conn.execute("SELECT wallet_balance_minor FROM buyers WHERE id=?", (row["buyer_id"],)).fetchone()[0]
            else:
                balance = self._apply_delta(row["buyer_id"], -row["amount_minor"], reason, order_id)
                self.conn.execute("UPDATE holds SET state='SETTLED' WHERE order_id=?", (order_id,))
        except Exception:
            self.conn.execute("ROLLBACK")
            raise
        self.conn.execute("COMMIT")
        return int(balance)

    def release_hold(self, order_id: str) -> None:
        self.conn.execute("UPDATE holds SET state='RELEASED' WHERE order_id=? AND state='HELD'", (order_id,))

    def hold_state(self, order_id: str) -> str | None:
        row = self.conn.execute("SELECT state FROM holds WHERE order_id=?", (order_id,)).fetchone()
        return row["state"] if row else None

    def save_payment_ref(
        self,
        *,
        order_id: str,
        provider: str,
        external_id: str,
        amount_minor: int,
        currency: str,
        status: str = "CREATED",
        payment_id: str | None = None,
    ) -> None:
        now = now_utc().isoformat()
        self.conn.execute(
            "INSERT OR REPLACE INTO payment_refs(order_id,provider,external_id,status,amount_minor,currency,payment_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (order_id, provider, external_id, status, amount_minor, currency, payment_id, now, now),
        )

    def update_payment_ref(self, external_id: str, *, status: str, payment_id: str | None = None) -> None:
        self.conn.execute(
            "UPDATE payment_refs SET status=?, payment_id=COALESCE(?, payment_id), updated_at=? WHERE external_id=?",
            (status, payment_id, now_utc().isoformat(), external_id),
        )

    def get_payment_ref_by_order(self, order_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM payment_refs WHERE order_id=?", (order_id,)).fetchone()
        return dict(row) if row else None

    def get_payment_ref_by_external(self, external_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM payment_refs WHERE external_id=?", (external_id,)).fetchone()
        return dict(row) if row else None

    def has_idempotency_key(self, key: str) -> bool:
        return self.conn.execute("SELECT 1 FROM orders WHERE idempotency_key=?", (key,)).fetchone() is not None

    def ledger_entries(self, order_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute("SELECT * FROM ledger WHERE order_id=? ORDER BY id", (order_id,)).fetchall()
        return [dict(row) for row in rows]

    def has_ledger_entry(self, order_id: str) -> bool:
        return self.conn.execute("SELECT 1 FROM ledger WHERE order_id=? AND delta < 0", (order_id,)).fetchone() is not None

    def append_audit(self, actor: str, event_type: str, payload: dict[str, Any]) -> AuditEvent:
        last = self.conn.execute("SELECT hash FROM audit_log ORDER BY seq DESC LIMIT 1").fetchone()
        prev_hash = last[0] if last else "GENESIS"
        body = {"actor": actor, "event_type": event_type, "payload": payload, "prev_hash": prev_hash}
        event_hash = digest(body)
        cur = self.conn.execute("INSERT INTO audit_log(ts,actor,event_type,payload_json,prev_hash,hash) VALUES(?,?,?,?,?,?)", (now_utc().isoformat(), actor, event_type, json.dumps(payload, sort_keys=True), prev_hash, event_hash))
        return AuditEvent(seq=cur.lastrowid, actor=actor, event_type=event_type, payload=payload, prev_hash=prev_hash, hash=event_hash)

    def audit_events(self) -> list[AuditEvent]:
        rows = self.conn.execute("SELECT * FROM audit_log ORDER BY seq").fetchall()
        return [AuditEvent(seq=r["seq"], ts=r["ts"], actor=r["actor"], event_type=r["event_type"], payload=json.loads(r["payload_json"]), prev_hash=r["prev_hash"], hash=r["hash"]) for r in rows]

    def verify_audit_chain(self) -> None:
        previous = "GENESIS"
        for event in self.audit_events():
            body = {"actor": event.actor, "event_type": event.event_type, "payload": event.payload, "prev_hash": previous}
            if event.prev_hash != previous or event.hash != digest(body):
                raise ReplayError(f"audit chain broken at sequence {event.seq}")
            previous = event.hash
