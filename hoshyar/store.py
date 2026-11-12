from __future__ import annotations

from collections import defaultdict
from contextlib import contextmanager
from dataclasses import asdict
from threading import local
from datetime import datetime
import json
from pathlib import Path
import sqlite3

from .models import Agent, Intent, Lead, Listing, Message, Tenant
from .service import HoshyarService


class SqliteStore:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = str(database_path)
        self._local = local()
        with self._connection() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS application_state (id INTEGER PRIMARY KEY CHECK (id = 1), payload TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS api_keys (key_hash TEXT PRIMARY KEY, tenant_id TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS member_sessions (token_hash TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, agent_id TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS channel_secrets (tenant_id TEXT NOT NULL, channel TEXT NOT NULL, secret_hash TEXT NOT NULL, PRIMARY KEY (tenant_id, channel))"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS channel_deliveries (tenant_id TEXT NOT NULL, channel TEXT NOT NULL, external_id TEXT NOT NULL, lead_id TEXT NOT NULL, PRIMARY KEY (tenant_id, channel, external_id))"
            )

    def load(self) -> HoshyarService:
        with self._connection() as connection:
            row = connection.execute("SELECT payload FROM application_state WHERE id = 1").fetchone()
        if row is None:
            return HoshyarService()
        data = json.loads(row[0])
        service = HoshyarService()
        service.tenants = {item["id"]: Tenant(**item) for item in data["tenants"]}
        service.agents = {item["id"]: Agent(**{"role": "agent", **item}) for item in data["agents"]}
        service.listings = {item["id"]: self._listing(item) for item in data["listings"]}
        service.baselines = data["baselines"]
        service.referrals = defaultdict(set, {key: set(value) for key, value in data["referrals"].items()})
        service.pilot_tenants = set(data["pilot_tenants"])
        for item in data["leads"]:
            item["created_at"] = datetime.fromisoformat(item["created_at"])
            item["intent"] = Intent(**item["intent"])
            item["messages"] = [
                Message(**{**message, "sent_at": datetime.fromisoformat(message["sent_at"])})
                for message in item["messages"]
            ]
            lead = Lead(**item)
            service.leads[lead.id] = lead
        return service

    @staticmethod
    def _listing(item: dict) -> Listing:
        """Older snapshots stored a single price and no deal type; keep them readable as sale listings."""
        return Listing(
            id=item["id"], tenant_id=item["tenant_id"], title=item["title"],
            neighborhood=item["neighborhood"], bedrooms=item["bedrooms"],
            deal_type=item.get("deal_type", "sale"), price=item.get("price"),
            deposit=item.get("deposit"), rent=item.get("rent"),
        )

    def save(self, service: HoshyarService) -> None:
        payload = json.dumps({
            "tenants": [asdict(item) for item in service.tenants.values()],
            "agents": [asdict(item) for item in service.agents.values()],
            "leads": [asdict(item) for item in service.leads.values()],
            "listings": [asdict(item) for item in service.listings.values()],
            "baselines": service.baselines,
            "referrals": {key: sorted(value) for key, value in service.referrals.items()},
            "pilot_tenants": sorted(service.pilot_tenants),
        }, default=lambda value: value.isoformat() if isinstance(value, datetime) else TypeError())
        with self._connection() as connection:
            connection.execute(
                "INSERT INTO application_state (id, payload) VALUES (1, ?) ON CONFLICT(id) DO UPDATE SET payload = excluded.payload",
                (payload,),
            )

    def save_api_key(self, key_hash: str, tenant_id: str) -> None:
        with self._connection() as connection:
            connection.execute("INSERT INTO api_keys (key_hash, tenant_id) VALUES (?, ?)", (key_hash, tenant_id))

    def save_session(self, token_hash: str, tenant_id: str, agent_id: str) -> None:
        with self._connection() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO member_sessions (token_hash, tenant_id, agent_id) VALUES (?, ?, ?)",
                (token_hash, tenant_id, agent_id),
            )

    def session_owner(self, token_hash: str) -> tuple[str, str] | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT tenant_id, agent_id FROM member_sessions WHERE token_hash = ?", (token_hash,)
            ).fetchone()
        return (row[0], row[1]) if row else None

    def delete_session(self, token_hash: str) -> None:
        with self._connection() as connection:
            connection.execute("DELETE FROM member_sessions WHERE token_hash = ?", (token_hash,))

    def save_channel_secret(self, tenant_id: str, channel: str, secret_hash: str) -> None:
        with self._connection() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO channel_secrets (tenant_id, channel, secret_hash) VALUES (?, ?, ?)",
                (tenant_id, channel, secret_hash),
            )

    def channel_secret_hash(self, tenant_id: str, channel: str) -> str | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT secret_hash FROM channel_secrets WHERE tenant_id = ? AND channel = ?", (tenant_id, channel)
            ).fetchone()
        return row[0] if row else None

    def delivered_lead(self, tenant_id: str, channel: str, external_id: str) -> str | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT lead_id FROM channel_deliveries WHERE tenant_id = ? AND channel = ? AND external_id = ?",
                (tenant_id, channel, external_id),
            ).fetchone()
        return row[0] if row else None

    def record_delivery(self, tenant_id: str, channel: str, external_id: str, lead_id: str) -> None:
        with self._connection() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO channel_deliveries (tenant_id, channel, external_id, lead_id) VALUES (?, ?, ?, ?)",
                (tenant_id, channel, external_id, lead_id),
            )

    def tenant_for_api_key(self, key_hash: str) -> str | None:
        with self._connection() as connection:
            row = connection.execute("SELECT tenant_id FROM api_keys WHERE key_hash = ?", (key_hash,)).fetchone()
        return row[0] if row else None

    @contextmanager
    def transaction(self):
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._local.connection = connection
            try:
                yield
            finally:
                del self._local.connection

    @contextmanager
    def _connection(self):
        active = getattr(self._local, "connection", None)
        if active is not None:
            yield active
            return
        connection = sqlite3.connect(self.database_path, timeout=15)
        try:
            with connection:
                yield connection
        finally:
            connection.close()
