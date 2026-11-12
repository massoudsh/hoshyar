from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from statistics import mean

from .intent import extract_intent, merge_intent
from .models import Agent, Lead, Listing, Message, Tenant, new_id


PILOT_LIMIT = 5


class HoshyarService:
    """In-memory product core; persistence and channel adapters belong at the boundary."""

    def __init__(self) -> None:
        self.tenants: dict[str, Tenant] = {}
        self.agents: dict[str, Agent] = {}
        self.leads: dict[str, Lead] = {}
        self.listings: dict[str, Listing] = {}
        self.baselines: dict[str, dict[str, float]] = {}
        self.referrals: dict[str, set[str]] = defaultdict(set)
        self.pilot_tenants: set[str] = set()

    def create_tenant(self, name: str) -> Tenant:
        tenant = Tenant(id=new_id("tenant"), name=name)
        self.tenants[tenant.id] = tenant
        return tenant

    def add_agent(self, tenant_id: str, name: str, role: str = "agent", password_hash: str | None = None) -> Agent:
        self._tenant(tenant_id)
        if role not in {"manager", "agent"}:
            raise ValueError("role must be manager or agent")
        agent = Agent(id=new_id("agent"), tenant_id=tenant_id, name=name, role=role, password_hash=password_hash)
        self.agents[agent.id] = agent
        return agent

    def set_password(self, tenant_id: str, agent_id: str, password_hash: str) -> Agent:
        agent = self._agent(tenant_id, agent_id)
        agent.password_hash = password_hash
        return agent

    def manager_count(self, tenant_id: str) -> int:
        self._tenant(tenant_id)
        return sum(1 for agent in self.agents.values() if agent.tenant_id == tenant_id and agent.role == "manager")

    def ingest_message(
        self,
        tenant_id: str,
        contact: str,
        body: str,
        channel: str,
        direction: str = "inbound",
        sent_at: datetime | None = None,
        agent_id: str | None = None,
        name: str | None = None,
    ) -> Lead:
        self._tenant(tenant_id)
        if direction not in {"inbound", "outbound"}:
            raise ValueError("direction must be inbound or outbound")
        if agent_id is not None:
            self._agent(tenant_id, agent_id)
        sent_at = sent_at or datetime.now(timezone.utc)
        lead = self._lead_by_contact(tenant_id, contact)
        if lead is None:
            lead = Lead(
                id=new_id("lead"), tenant_id=tenant_id, contact=contact, name=name,
                state="new", assigned_agent_id=agent_id, created_at=sent_at,
            )
            self.leads[lead.id] = lead
        elif name and not lead.name:
            lead.name = name

        message = Message(
            id=new_id("message"), tenant_id=tenant_id, lead_id=lead.id, channel=channel,
            direction=direction, body=body, sent_at=sent_at, agent_id=agent_id,
        )
        lead.messages.append(message)
        if direction == "inbound":
            lead.intent = merge_intent(lead.intent, extract_intent(body))
            lead.state = "unanswered"
        else:
            lead.assigned_agent_id = agent_id or lead.assigned_agent_id
            lead.state = "in_progress"
        return lead

    def assign_agent(self, tenant_id: str, lead_id: str, agent_id: str) -> Lead:
        lead = self._lead(tenant_id, lead_id)
        self._agent(tenant_id, agent_id)
        lead.assigned_agent_id = agent_id
        return lead

    def add_listing(
        self,
        tenant_id: str,
        title: str,
        neighborhood: str,
        bedrooms: int,
        deal_type: str = "sale",
        price: int | None = None,
        deposit: int | None = None,
        rent: int | None = None,
    ) -> Listing:
        self._tenant(tenant_id)
        if bedrooms < 0:
            raise ValueError("bedrooms cannot be negative")
        if deal_type not in {"sale", "rent"}:
            raise ValueError("deal_type must be sale or rent")
        amounts = {"price": price, "deposit": deposit, "rent": rent}
        if any(value is not None and value <= 0 for value in amounts.values()):
            raise ValueError("listing amounts must be positive")
        if deal_type == "sale":
            if not price or deposit or rent:
                raise ValueError("a sale listing needs only a sale price")
            deposit = rent = None
        elif not deposit and not rent:
            raise ValueError("a rental listing needs a deposit or a monthly rent")
        else:
            price = None
        now = datetime.now(timezone.utc)
        listing = Listing(
            id=new_id("listing"), tenant_id=tenant_id, title=title, neighborhood=neighborhood,
            deal_type=deal_type, bedrooms=bedrooms, price=price, deposit=deposit, rent=rent,
            created_at=now, updated_at=now,
        )
        self.listings[listing.id] = listing
        return listing

    def update_listing(self, tenant_id: str, listing_id: str, **changes) -> Listing:
        """Apply only the fields the caller sent; re-validate the merged result like a new listing."""
        listing = self._listing(tenant_id, listing_id)
        merged = {
            "title": changes.get("title", listing.title),
            "neighborhood": changes.get("neighborhood", listing.neighborhood),
            "bedrooms": changes.get("bedrooms", listing.bedrooms),
            "deal_type": changes.get("deal_type", listing.deal_type),
            "price": changes.get("price", listing.price),
            "deposit": changes.get("deposit", listing.deposit),
            "rent": changes.get("rent", listing.rent),
        }
        if not isinstance(merged["title"], str) or not merged["title"].strip():
            raise ValueError("title is required")
        if not isinstance(merged["neighborhood"], str) or not merged["neighborhood"].strip():
            raise ValueError("neighborhood is required")
        if isinstance(merged["bedrooms"], bool) or not isinstance(merged["bedrooms"], int) or merged["bedrooms"] < 0:
            raise ValueError("bedrooms cannot be negative")
        if merged["deal_type"] not in {"sale", "rent"}:
            raise ValueError("deal_type must be sale or rent")
        amounts = {name: merged[name] for name in ("price", "deposit", "rent")}
        if any(value is not None and (isinstance(value, bool) or not isinstance(value, int) or value <= 0)
               for value in amounts.values()):
            raise ValueError("listing amounts must be positive")
        if merged["deal_type"] == "sale":
            if not merged["price"] or merged["deposit"] or merged["rent"]:
                raise ValueError("a sale listing needs only a sale price")
            merged["deposit"] = merged["rent"] = None
        elif not merged["deposit"] and not merged["rent"]:
            raise ValueError("a rental listing needs a deposit or a monthly rent")
        else:
            merged["price"] = None
        for name, value in merged.items():
            setattr(listing, name, value.strip() if isinstance(value, str) else value)
        listing.updated_at = datetime.now(timezone.utc)
        return listing

    def delete_listing(self, tenant_id: str, listing_id: str) -> None:
        self._listing(tenant_id, listing_id)
        del self.listings[listing_id]

    def stale_listings(self, tenant_id: str, days: int = 14, now: datetime | None = None) -> list[dict]:
        """فایلs nobody has touched for a while; an old فایل is usually sold or rented already."""
        self._tenant(tenant_id)
        if days <= 0:
            raise ValueError("days must be positive")
        now = now or datetime.now(timezone.utc)
        stale = []
        for listing in self.listings.values():
            if listing.tenant_id != tenant_id:
                continue
            touched = listing.updated_at or listing.created_at
            if touched is None:
                continue
            age_days = (now - touched).total_seconds() / 86400
            if age_days >= days:
                stale.append({"listing": listing, "age_days": round(age_days, 1)})
        return sorted(stale, key=lambda item: -item["age_days"])

    def dashboard(self, tenant_id: str, now: datetime | None = None, overdue_hours: int = 24,
                  cold_after_days: int = 14) -> dict:
        self._tenant(tenant_id)
        now = now or datetime.now(timezone.utc)
        leads = self._tenant_leads(tenant_id)
        at_risk = [lead for lead in leads if self._is_overdue(lead, now, overdue_hours)]
        cold = [lead for lead in leads if self._is_cold(lead, now, cold_after_days)]
        return {
            "active_lead_count": sum(lead.state not in {"cold", "converted"} for lead in leads),
            "at_risk_leads": [self._lead_summary(lead) for lead in at_risk],
            "unassigned_leads": [self._lead_summary(lead) for lead in leads if lead.assigned_agent_id is None],
            "cold_leads": [self._lead_summary(lead) for lead in cold],
        }

    def mark_cold(self, tenant_id: str, lead_id: str) -> Lead:
        lead = self._lead(tenant_id, lead_id)
        lead.state = "cold"
        return lead

    def followups(self, tenant_id: str, agent_id: str | None = None, now: datetime | None = None,
                  overdue_hours: int = 24) -> list[dict]:
        """Every lead waiting on us, soonest deadline first.

        Only a lead whose last message is inbound is waiting; the age is measured from that message.
        """
        self._tenant(tenant_id)
        if agent_id is not None:
            self._agent(tenant_id, agent_id)
        now = now or datetime.now(timezone.utc)
        queue = []
        for lead in self._tenant_leads(tenant_id):
            if agent_id is not None and lead.assigned_agent_id != agent_id:
                continue
            if lead.state in {"cold", "converted"}:
                continue
            if not lead.messages or lead.messages[-1].direction != "inbound":
                continue
            waiting_hours = (now - lead.messages[-1].sent_at).total_seconds() / 3600
            if waiting_hours >= overdue_hours * 3:
                bucket = "critical"
            elif waiting_hours >= overdue_hours:
                bucket = "overdue"
            elif lead.assigned_agent_id is None:
                bucket = "unassigned"
            else:
                bucket = "waiting"
            matches = len(self.matching_listings(tenant_id, lead.id))
            owner = self.agents.get(lead.assigned_agent_id) if lead.assigned_agent_id else None
            queue.append({
                "lead": self._lead_summary(lead),
                "waiting_hours": round(waiting_hours, 1),
                "bucket": bucket,
                "match_count": matches,
                "owner_name": owner.name if owner else None,
                "score": self._followup_score(bucket, waiting_hours, matches),
            })
        return sorted(queue, key=lambda item: (-item["score"], -item["waiting_hours"]))

    @staticmethod
    def _followup_score(bucket: str, waiting_hours: float, match_count: int) -> float:
        # Being late dominates; an answerable lead with real فایلs matters more than one without.
        weight = {"critical": 30, "overdue": 20, "unassigned": 10, "waiting": 0}[bucket]
        return weight + min(waiting_hours, 72) * 0.5 + min(match_count, 5) * 2

    def matching_listings(self, tenant_id: str, lead_id: str) -> list[dict]:
        lead = self._lead(tenant_id, lead_id)
        if lead.intent.purpose not in {"buy", "rent"}:
            return []
        deal_type = "rent" if lead.intent.purpose == "rent" else "sale"
        matches = []
        for listing in self.listings.values():
            if listing.tenant_id != tenant_id or listing.deal_type != deal_type:
                continue
            # A known budget is a hard constraint: an unaffordable listing is not a match, however close it is.
            if deal_type == "sale":
                budget, amount = lead.intent.price, listing.price
                if budget and (amount is None or amount > budget):
                    continue
            elif not self._rent_fits(lead.intent.deposit, lead.intent.rent, listing):
                continue
            score = 0
            reasons = []
            if lead.intent.neighborhood and listing.neighborhood == lead.intent.neighborhood:
                score += 2
                reasons.append(f"same neighborhood: {listing.neighborhood}")
            if deal_type == "sale" and lead.intent.price and listing.price:
                # Closer to the ceiling is a better fit; a فایل at half the budget is rarely what was asked for.
                headroom = 1 - listing.price / lead.intent.price
                if headroom <= 0.2:
                    score += 1
                    reasons.append("price close to the stated budget")
            elif deal_type == "rent":
                if lead.intent.deposit and listing.deposit:
                    reasons.append("deposit within budget")
                if lead.intent.rent and listing.rent:
                    reasons.append("monthly rent within budget")
            if score:
                matches.append({"listing": listing, "score": score, "reasons": reasons})
        return sorted(matches, key=lambda match: -match["score"])

    @staticmethod
    def _rent_fits(deposit: int | None, rent: int | None, listing: Listing) -> bool:
        deposit_fits = not deposit or (listing.deposit is not None and listing.deposit <= deposit)
        rent_fits = not rent or (listing.rent is not None and listing.rent <= rent)
        return deposit_fits and rent_fits and bool(deposit or rent)

    def pricing_alerts(self, tenant_id: str, under_market_ratio: float = 0.85) -> list[dict]:
        self._tenant(tenant_id)
        alerts = []
        listings = [listing for listing in self.listings.values() if listing.tenant_id == tenant_id]
        for listing in listings:
            peers = [
                other.price for other in listings
                if other.id != listing.id and other.neighborhood == listing.neighborhood
                and other.deal_type == listing.deal_type and other.price is not None
            ]
            if listing.price is not None and peers and listing.price < mean(peers) * under_market_ratio:
                alerts.append({"listing": listing, "market_average": int(mean(peers))})
        return alerts

    def set_baseline(self, tenant_id: str, response_hours: float, conversion_rate: float) -> None:
        self._tenant(tenant_id)
        self.baselines[tenant_id] = {"response_hours": response_hours, "conversion_rate": conversion_rate}

    def agent_performance(self, tenant_id: str, since: datetime | None = None,
                          until: datetime | None = None) -> list[dict]:
        """Per-advisor numbers for a period; a reply counts for the advisor who sent it."""
        self._tenant(tenant_id)
        if since and until and since > until:
            raise ValueError("since must be before until")
        reports = []
        tenant_leads = self._tenant_leads(tenant_id)
        for agent in self.agents.values():
            if agent.tenant_id != tenant_id:
                continue
            leads = [lead for lead in tenant_leads if lead.assigned_agent_id == agent.id]
            # Scan every lead, not just the ones assigned now: a reassigned lead still credits
            # the advisor who actually sent each reply.
            delays = [
                delay for lead in tenant_leads
                for delay in self._response_delays(lead, since=since, until=until, agent_id=agent.id)
            ]
            converted = sum(lead.state == "converted" for lead in leads)
            reports.append({
                "agent": agent,
                "lead_count": len(leads),
                "unanswered_count": sum(lead.state == "unanswered" for lead in leads),
                "conversion_rate": converted / len(leads) if leads else 0.0,
                "response_hours": mean(delays) if delays else None,
                "replies": len(delays),
            })
        return reports

    def performance_report(self, tenant_id: str, since: datetime | None = None,
                           until: datetime | None = None) -> dict:
        """A period report a manager can hand over: office totals plus one row per advisor."""
        self._tenant(tenant_id)
        rows = self.agent_performance(tenant_id, since=since, until=until)
        office_delays = [
            delay for lead in self._tenant_leads(tenant_id)
            for delay in self._response_delays(lead, since=since, until=until)
        ]
        return {
            "since": since,
            "until": until,
            "office": {
                "response_hours": mean(office_delays) if office_delays else None,
                "replies": len(office_delays),
            },
            "agents": rows,
        }

    def enroll_pilot(self, tenant_id: str) -> None:
        self._tenant(tenant_id)
        if tenant_id not in self.pilot_tenants and len(self.pilot_tenants) >= PILOT_LIMIT:
            raise ValueError(f"pilot is limited to {PILOT_LIMIT} offices")
        self.pilot_tenants.add(tenant_id)

    def mark_converted(self, tenant_id: str, lead_id: str) -> Lead:
        lead = self._lead(tenant_id, lead_id)
        lead.state = "converted"
        return lead

    def measurement_report(self, tenant_id: str) -> dict:
        self._tenant(tenant_id)
        leads = self._tenant_leads(tenant_id)
        delays = [delay for lead in leads for delay in self._response_delays(lead)]
        current = {
            "response_hours": mean(delays) if delays else None,
            "conversion_rate": (sum(lead.state == "converted" for lead in leads) / len(leads)) if leads else 0.0,
        }
        baseline = self.baselines.get(tenant_id)
        change = None
        if baseline and current["response_hours"] is not None:
            change = {
                "response_hours": current["response_hours"] - baseline["response_hours"],
                "conversion_rate": current["conversion_rate"] - baseline["conversion_rate"],
            }
        return {"baseline": baseline, "current": current, "change": change}

    def record_referral(self, tenant_id: str, referred_tenant_id: str) -> None:
        self._tenant(tenant_id)
        self._tenant(referred_tenant_id)
        if tenant_id == referred_tenant_id:
            raise ValueError("a tenant cannot refer itself")
        self.referrals[tenant_id].add(referred_tenant_id)

    def _tenant(self, tenant_id: str) -> Tenant:
        try:
            return self.tenants[tenant_id]
        except KeyError as error:
            raise ValueError("unknown tenant") from error

    def _agent(self, tenant_id: str, agent_id: str) -> Agent:
        try:
            agent = self.agents[agent_id]
        except KeyError as error:
            raise ValueError("unknown agent") from error
        if agent.tenant_id != tenant_id:
            raise ValueError("cross-tenant access denied")
        return agent

    def _listing(self, tenant_id: str, listing_id: str) -> Listing:
        try:
            listing = self.listings[listing_id]
        except KeyError as error:
            raise ValueError("unknown listing") from error
        if listing.tenant_id != tenant_id:
            raise ValueError("cross-tenant access denied")
        return listing

    def _lead(self, tenant_id: str, lead_id: str) -> Lead:
        try:
            lead = self.leads[lead_id]
        except KeyError as error:
            raise ValueError("unknown lead") from error
        if lead.tenant_id != tenant_id:
            raise ValueError("cross-tenant access denied")
        return lead

    def _lead_by_contact(self, tenant_id: str, contact: str) -> Lead | None:
        return next((lead for lead in self._tenant_leads(tenant_id) if lead.contact == contact), None)

    def _tenant_leads(self, tenant_id: str) -> list[Lead]:
        return [lead for lead in self.leads.values() if lead.tenant_id == tenant_id]

    @staticmethod
    def _response_delays(lead: Lead, since: datetime | None = None, until: datetime | None = None,
                         agent_id: str | None = None) -> list[float]:
        """Hours between an inbound message and the reply that answered it.

        A reply is attributed to the advisor who sent it, so a lead reassigned mid-conversation
        credits each reply to the right person. `since`/`until` filter on the reply time.
        """
        delays: list[float] = []
        waiting_since: datetime | None = None
        for message in lead.messages:
            if message.direction == "inbound":
                waiting_since = waiting_since or message.sent_at
            elif waiting_since is not None:
                if agent_id is not None and message.agent_id != agent_id:
                    waiting_since = None
                    continue
                if since is not None and message.sent_at < since:
                    waiting_since = None
                    continue
                if until is not None and message.sent_at > until:
                    waiting_since = None
                    continue
                delays.append((message.sent_at - waiting_since).total_seconds() / 3600)
                waiting_since = None
        return delays

    @staticmethod
    def _is_cold(lead: Lead, now: datetime, cold_after_days: int) -> bool:
        """A lead nobody has heard from for weeks is cold; a converted one is never cold."""
        if lead.state in {"cold", "converted"} or not lead.messages:
            return False
        return lead.messages[-1].sent_at <= now - timedelta(days=cold_after_days)

    @staticmethod
    def _is_overdue(lead: Lead, now: datetime, overdue_hours: int) -> bool:
        if not lead.messages or lead.messages[-1].direction != "inbound":
            return False
        return lead.messages[-1].sent_at <= now - timedelta(hours=overdue_hours)

    @staticmethod
    def _lead_summary(lead: Lead) -> dict:
        return {
            "id": lead.id,
            "name": lead.name,
            "contact": lead.contact,
            "state": lead.state,
            "assigned_agent_id": lead.assigned_agent_id,
            "intent": lead.intent,
        }
