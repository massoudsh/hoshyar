from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal
from uuid import uuid4

LeadState = Literal["new", "in_progress", "unanswered", "cold", "converted"]
DealType = Literal["sale", "rent"]


@dataclass(frozen=True)
class Intent:
    purpose: str | None = None
    price: int | None = None
    deposit: int | None = None
    rent: int | None = None
    neighborhood: str | None = None
    urgency: str | None = None
    confidence: float = 0.0


@dataclass
class Tenant:
    id: str
    name: str


AgentRole = Literal["manager", "agent"]


@dataclass
class Agent:
    id: str
    tenant_id: str
    name: str
    role: AgentRole = "agent"
    # Salted PBKDF2 hash; the plain password is never stored or returned.
    password_hash: str | None = None


@dataclass
class Message:
    id: str
    tenant_id: str
    lead_id: str
    channel: str
    direction: Literal["inbound", "outbound"]
    body: str
    sent_at: datetime
    agent_id: str | None = None


@dataclass
class Lead:
    id: str
    tenant_id: str
    contact: str
    name: str | None
    state: LeadState
    assigned_agent_id: str | None
    created_at: datetime
    intent: Intent = field(default_factory=Intent)
    messages: list[Message] = field(default_factory=list)


@dataclass
class Listing:
    id: str
    tenant_id: str
    title: str
    neighborhood: str
    deal_type: DealType
    bedrooms: int
    price: int | None = None
    deposit: int | None = None
    rent: int | None = None
    area: float | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    verified_at: datetime | None = None
    verified_by: str | None = None
    # Every amount change, oldest first; "at" plus whichever of price/deposit/rent was in force.
    price_history: list[dict] = field(default_factory=list)


@dataclass
class SavedSearch:
    """A standing request: any فایل that fits alerts the advisors without re-asking the buyer."""

    id: str
    tenant_id: str
    name: str
    deal_type: DealType
    max_price: int | None = None
    max_deposit: int | None = None
    max_rent: int | None = None
    neighborhood: str | None = None
    bedrooms: int | None = None
    lead_id: str | None = None
    created_at: datetime | None = None


ViewingStatus = Literal["scheduled", "done", "cancelled"]


@dataclass
class Viewing:
    id: str
    tenant_id: str
    lead_id: str
    listing_id: str
    starts_at: datetime
    agent_id: str | None = None
    status: ViewingStatus = "scheduled"
    note: str | None = None


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"
