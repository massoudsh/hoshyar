from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime
from hashlib import sha256
import hmac
import json
import secrets
from typing import Any

from .channels import CHANNELS, ChannelPayloadError, normalize
from .service import HoshyarService
from .store import SqliteStore


class HoshyarApi:
    def __init__(self, store: SqliteStore, bootstrap_key: str) -> None:
        if not bootstrap_key:
            raise ValueError("bootstrap_key is required")
        self.store = store
        self.bootstrap_key = bootstrap_key

    def handle(self, method: str, path: str, headers: dict[str, str], body: bytes = b"") -> tuple[int, dict[str, Any]]:
        with self.store.transaction():
            return self._handle(method, path, headers, body)

    def _handle(self, method: str, path: str, headers: dict[str, str], body: bytes) -> tuple[int, dict[str, Any]]:
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
            if method == "POST" and path == "/v1/sessions":
                service = self.store.load()
                agent = self._find_member(service, self._required(payload, "tenant"), self._required(payload, "name"))
                token = secrets.token_urlsafe(32)
                self.store.save_session(self._hash(token), agent.tenant_id, agent.id)
                return 201, {"token": token, "tenant_id": agent.tenant_id, "member": self._json(agent)}
            if method == "POST" and path.startswith("/v1/channels/"):
                return self._receive_channel(path, headers, payload)
            if method == "DELETE" and path == "/v1/sessions":
                token = headers.get("x-session-token", "")
                if token:
                    self.store.delete_session(self._hash(token))
                return 200, {"status": "signed out"}

            parts = path.strip("/").split("/")
            if len(parts) < 3 or parts[:2] != ["v1", "tenants"]:
                return 404, {"error": "not found"}
            tenant_id = parts[2]
            member_id = self._authorize_tenant(headers, tenant_id)
            service = self.store.load()
            service._tenant(tenant_id)
            member = service._agent(tenant_id, member_id) if member_id else None
            if member is not None and member.role != "manager":
                if parts[3:] in (["agents"], ["listings"], ["baselines"], ["referrals"]) or (
                    len(parts) == 5 and parts[3] == "channels"
                ):
                    raise PermissionError("manager role required")
                if len(parts) == 6 and parts[3] == "leads" and parts[5] == "assignment":
                    raise PermissionError("manager role required")

            if method == "GET" and parts[3:] == ["workspace"]:
                leads = service._tenant_leads(tenant_id)
                if member is not None and member.role != "manager":
                    leads = [lead for lead in leads if lead.assigned_agent_id == member.id]
                return 200, self._json({
                    "tenant": service._tenant(tenant_id),
                    "viewer": member,
                    "leads": leads,
                    "followups": service.followups(
                        tenant_id, None if member is None or member.role == "manager" else member.id
                    ),
                    "agents": [agent for agent in service.agents.values() if agent.tenant_id == tenant_id],
                    "listings": [listing for listing in service.listings.values() if listing.tenant_id == tenant_id],
                    "dashboard": service.dashboard(tenant_id),
                    "performance": service.agent_performance(tenant_id),
                    "measurement": service.measurement_report(tenant_id),
                })
            if method == "POST" and len(parts) == 6 and parts[3] == "leads" and parts[5] == "assignment":
                lead = service.assign_agent(tenant_id, parts[4], self._required(payload, "agent_id"))
                self.store.save(service)
                return 200, {"lead": self._json(lead)}
            if method == "POST" and parts[3:] == ["agents"]:
                agent = service.add_agent(tenant_id, self._required(payload, "name"), payload.get("role", "agent"))
                self.store.save(service)
                return 201, {"agent": self._json(agent)}
            if method == "GET" and parts[3:] == ["followups"]:
                return 200, {"followups": self._json(service.followups(tenant_id))}
            if method == "POST" and len(parts) == 5 and parts[3] == "channels":
                channel = parts[4]
                if channel not in CHANNELS:
                    raise ValueError(f"channel must be one of {', '.join(CHANNELS)}")
                secret = secrets.token_urlsafe(32)
                self.store.save_channel_secret(tenant_id, channel, self._hash(secret))
                return 201, {"channel": channel, "secret": secret}
            if method == "GET" and parts[3:] == ["me"]:
                return 200, {"viewer": self._json(member)}
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
                    tenant_id=tenant_id,
                    title=self._required(payload, "title"),
                    neighborhood=self._required(payload, "neighborhood"),
                    bedrooms=self._integer(payload, "bedrooms"),
                    deal_type=payload.get("deal_type", "sale"),
                    price=self._optional_integer(payload, "price"),
                    deposit=self._optional_integer(payload, "deposit"),
                    rent=self._optional_integer(payload, "rent"),
                )
                self.store.save(service)
                return 201, {"listing": self._json(listing)}
            if method == "GET" and len(parts) == 6 and parts[3] == "leads" and parts[5] == "matches":
                return 200, {"matches": self._json(service.matching_listings(tenant_id, parts[4]))}
            return 404, {"error": "not found"}
        except PermissionError as error:
            return 401, {"error": str(error)}
        except ChannelPayloadError as error:
            return 422, {"error": str(error)}
        except ValueError as error:
            return 400, {"error": str(error)}

    def _receive_channel(self, path: str, headers: dict[str, str], payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Accept a channel webhook: /v1/channels/{tenant_id}/{channel}, authenticated by that channel's secret."""
        parts = path.strip("/").split("/")
        if len(parts) != 4:
            return 404, {"error": "not found"}
        _, _, tenant_id, channel = parts
        expected = self.store.channel_secret_hash(tenant_id, channel)
        supplied = headers.get("x-channel-secret", "")
        if expected is None or not supplied or not hmac.compare_digest(self._hash(supplied), expected):
            raise PermissionError("invalid channel secret")
        message = normalize(channel, payload)
        if message["external_id"]:
            existing = self.store.delivered_lead(tenant_id, channel, message["external_id"])
            if existing:
                return 200, {"lead_id": existing, "duplicate": True}
        service = self.store.load()
        lead = service.ingest_message(
            tenant_id=tenant_id, contact=message["contact"], body=message["body"], channel=channel,
            sent_at=message["sent_at"], name=message["name"],
        )
        self.store.save(service)
        if message["external_id"]:
            self.store.record_delivery(tenant_id, channel, message["external_id"], lead.id)
        return 201, {"lead_id": lead.id, "duplicate": False}

    @staticmethod
    def _find_member(service: HoshyarService, tenant_id: str, name: str) -> Any:
        service._tenant(tenant_id)
        wanted = " ".join(name.split())
        if not wanted:
            raise ValueError("name is required")
        matches = [
            agent for agent in service.agents.values()
            if agent.tenant_id == tenant_id and " ".join(agent.name.split()) == wanted
        ]
        if not matches:
            raise PermissionError("no team member with that name")
        if len(matches) > 1:
            raise ValueError("more than one team member has that name")
        return matches[0]

    def _authorize_bootstrap(self, headers: dict[str, str]) -> None:
        supplied = headers.get("x-bootstrap-key", "")
        if not hmac.compare_digest(supplied, self.bootstrap_key):
            raise PermissionError("invalid bootstrap key")

    def _authorize_tenant(self, headers: dict[str, str], tenant_id: str) -> str | None:
        """Return the member id behind a session token, or None for the office-wide key."""
        token = headers.get("x-session-token", "")
        if token:
            owner = self.store.session_owner(self._hash(token))
            if owner is None or owner[0] != tenant_id:
                raise PermissionError("invalid session")
            return owner[1]
        api_key = headers.get("x-api-key", "")
        if not api_key or self.store.tenant_for_api_key(self._hash(api_key)) != tenant_id:
            raise PermissionError("invalid API key")
        return None

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
    def _optional_integer(payload: dict[str, Any], name: str) -> int | None:
        value = payload.get(name)
        if value is None:
            return None
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
