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
    created_at: datetime | None = None
    updated_at: datetime | None = None


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"
