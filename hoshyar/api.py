from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime
from hashlib import sha256
import hmac
import json
import secrets
from typing import Any

from .service import HoshyarService
from .store import SqliteStore


class HoshyarApi:
    def __init__(self, store: SqliteStore, bootstrap_key: str) -> None:
        if not bootstrap_key:
            raise ValueError("bootstrap_key is required")
        self.store = store
        self.bootstrap_key = bootstrap_key

    def handle(self, method: str, path: str, headers: dict[str, str], body: bytes = b"") -> tuple[int, dict[str, Any]]:
        try:
            payload = self._body(body)
            if method == "GET" and path == "/health":
                return 200, {"status": "ok"}
            if method == "POST" and path == "/v1/tenants":
                self._authorize_bootstrap(headers)
                service = self.store.load()
                tenant = service.create_tenant(self._required(payload, "name"))
                api_key = secrets.token_urlsafe(32)
                self.store.save(service)
                self.store.save_api_key(self._hash(api_key), tenant.id)
                return 201, {"tenant": self._json(tenant), "api_key": api_key}

            parts = path.strip("/").split("/")
            if len(parts) < 3 or parts[:2] != ["v1", "tenants"]:
                return 404, {"error": "not found"}
            tenant_id = parts[2]
            self._authorize_tenant(headers, tenant_id)
            service = self.store.load()
            service._tenant(tenant_id)

            if method == "POST" and parts[3:] == ["agents"]:
                agent = service.add_agent(tenant_id, self._required(payload, "name"))
                self.store.save(service)
                return 201, {"agent": self._json(agent)}
            if method == "POST" and parts[3:] == ["messages"]:
                lead = service.ingest_message(
                    tenant_id=tenant_id,
                    contact=self._required(payload, "contact"),
                    body=self._required(payload, "body"),
                    channel=self._required(payload, "channel"),
                    direction=payload.get("direction", "inbound"),
                    agent_id=payload.get("agent_id"),
                    name=payload.get("name"),
                )
                self.store.save(service)
                return 201, {"lead": self._json(lead)}
            if method == "GET" and parts[3:] == ["dashboard"]:
                return 200, self._json(service.dashboard(tenant_id))
            if method == "POST" and parts[3:] == ["listings"]:
                listing = service.add_listing(
                    tenant_id, self._required(payload, "title"), self._required(payload, "neighborhood"),
                    self._integer(payload, "price"), self._integer(payload, "bedrooms"),
                )
                self.store.save(service)
                return 201, {"listing": self._json(listing)}
            if method == "GET" and len(parts) == 6 and parts[3] == "leads" and parts[5] == "matches":
                return 200, {"matches": self._json(service.matching_listings(tenant_id, parts[4]))}
            return 404, {"error": "not found"}
        except PermissionError as error:
            return 401, {"error": str(error)}
        except ValueError as error:
            return 400, {"error": str(error)}

    def _authorize_bootstrap(self, headers: dict[str, str]) -> None:
        supplied = headers.get("x-bootstrap-key", "")
        if not hmac.compare_digest(supplied, self.bootstrap_key):
            raise PermissionError("invalid bootstrap key")

    def _authorize_tenant(self, headers: dict[str, str], tenant_id: str) -> None:
        api_key = headers.get("x-api-key", "")
        if not api_key or self.store.tenant_for_api_key(self._hash(api_key)) != tenant_id:
            raise PermissionError("invalid API key")

    @staticmethod
    def _body(body: bytes) -> dict[str, Any]:
        if not body:
            return {}
        parsed = json.loads(body)
        if not isinstance(parsed, dict):
            raise ValueError("JSON body must be an object")
        return parsed

    @staticmethod
    def _required(payload: dict[str, Any], name: str) -> str:
        value = payload.get(name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} is required")
        return value.strip()

    @staticmethod
    def _integer(payload: dict[str, Any], name: str) -> int:
        value = payload.get(name)
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{name} must be an integer")
        return value

    @staticmethod
    def _hash(value: str) -> str:
        return sha256(value.encode()).hexdigest()

    @classmethod
    def _json(cls, value: Any) -> Any:
        if is_dataclass(value):
            return cls._json(asdict(value))
        if isinstance(value, dict):
            return {key: cls._json(item) for key, item in value.items()}
        if isinstance(value, list):
            return [cls._json(item) for item in value]
        if isinstance(value, datetime):
            return value.isoformat()
        return value
