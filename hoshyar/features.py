"""Pure helpers behind the features borrowed from the 2026 market.

Each function is deterministic and dependency-free so the service stays the only
place that owns state and the API stays a thin translation layer.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from statistics import mean


# The market convention: a month of rent is treated as one sixth of the deposit.
RAHN_TO_RENT_DIVISOR = 6

# What the office charges for a closed deal.
COMMISSION_RATE_SALE = 0.005
COMMISSION_RATE_RENT = 0.25  # one quarter of a month's rent, paid by each side

# Bank profit rate used when we show what a mortgage-free loan would cost.
ANNUAL_PROFIT_RATE = 0.23

# یک فایل priced this much under its neighbourhood peers usually means a typo or a bait listing.
SUSPICIOUS_DISCOUNT = 0.7

# Data older than this is called out wherever a number is shown.
FRESHNESS_DAYS = 14


def price_at(listing, moment: datetime) -> int | None:
    """The sale price that was in force at `moment`, reconstructed from the change history."""
    history = getattr(listing, "price_history", None) or []
    amount = listing.price
    for change in history:
        if change["at"] > moment:
            break
        if "price" in change:
            amount = change["price"]
    return amount


def price_trend(listings, tenant_id: str, neighborhood: str | None = None,
                months: int = 6, now: datetime | None = None) -> dict:
    """Average sale price per month across the office's own files.

    Each month is measured from the price the file carried at the end of that month, so a
    re-priced file moves the whole history forward; that is what an advisor expects to see
    when the owner drops the price. Months without files are omitted, never filled with zero.
    """
    now = now or datetime.now(timezone.utc)
    scoped = [
        listing for listing in listings
        if listing.tenant_id == tenant_id and listing.deal_type == "sale"
        and (neighborhood is None or listing.neighborhood == neighborhood)
    ]
    buckets: dict[str, list[int]] = {}
    for offset in range(months - 1, -1, -1):
        year, month = now.year, now.month - offset
        while month <= 0:
            year, month = year - 1, month + 12
        end = datetime(year, month, 28, 23, 59, tzinfo=timezone.utc)
        if offset == 0:
            end = now
        prices = [
            amount for listing in scoped
            if (amount := price_at(listing, end)) is not None and listing.created_at and listing.created_at <= end
        ]
        if prices:
            buckets[f"{year:04d}-{month:02d}"] = prices
    points = [{"month": key, "average": int(mean(values)), "count": len(values)} for key, values in buckets.items()]
    change = None
    if len(points) >= 2 and points[0]["average"]:
        change = round((points[-1]["average"] - points[0]["average"]) / points[0]["average"] * 100, 1)
    return {"points": points, "change_percent": change}


def affordability(max_price: int | None = None, max_deposit: int | None = None,
                  max_rent: int | None = None, deal_type: str = "sale",
                  savings: int = 0, monthly_income: int | None = None,
                  profit_rate: float = ANNUAL_PROFIT_RATE) -> dict:
    """What a buyer or renter can actually commit to, the question Zillow's BuyAbility answers.

    Sale: the budget is the stated price, and a mortgage-free loan of (budget - cash) is priced
    at the bank profit rate. Rent: rahn is constrained by cash, and every 1M تومان of rahn
    frees one sixth of it in monthly rent using the market convention.
    """
    if profit_rate <= 0:
        raise ValueError("profit rate must be positive")
    if savings < 0:
        raise ValueError("savings cannot be negative")
    if monthly_income is not None and monthly_income < 0:
        raise ValueError("monthly income cannot be negative")

    if deal_type == "sale":
        budget = max_price
        if budget is None:
            return {"deal_type": "sale", "budget": None, "financed": None, "monthly_payment": None}
        financed = max(budget - savings, 0)
        monthly = financed * (profit_rate / 12) if financed else 0
        return {
            "deal_type": "sale",
            "budget": budget,
            "savings": savings,
            "financed": financed,
            "annual_profit_rate": profit_rate,
            "monthly_payment": round(monthly),
            "monthly_payment_share_of_income": round(monthly / monthly_income, 3) if monthly_income else None,
        }

    deposit = max_deposit
    rent = max_rent
    equivalent = None
    if deposit is not None or rent is not None:
        equivalent = (deposit or 0) + (rent or 0) * RAHN_TO_RENT_DIVISOR
    gap = max(deposit - savings, 0) if deposit is not None else None
    # If the cash on hand cannot cover the rahn, show the rent the buyer could pay instead.
    rent_with_savings = max(equivalent - savings, 0) // RAHN_TO_RENT_DIVISOR if equivalent is not None else None
    return {
        "deal_type": "rent",
        "max_deposit": deposit,
        "max_rent": rent,
        "savings": savings,
        "rahn_equivalent": equivalent,
        "deposit_gap": gap,
        "rent_with_savings": rent_with_savings if gap else rent,
    }


def convert_rahn(deposit: int, rent: int, target_deposit: int | None = None,
                 target_rent: int | None = None, divisor: int = RAHN_TO_RENT_DIVISOR) -> dict:
    """Convert between a رهن/اجاره mix and a single figure, the way Divar's filing tools do.

    Moving 1 تومان from the deposit to the rent (or back) moves the other side by `divisor`.
    Exactly one target may be given, or none to get both directions.
    """
    if deposit < 0 or rent < 0:
        raise ValueError("deposit and rent cannot be negative")
    if divisor <= 0:
        raise ValueError("divisor must be positive")
    if target_deposit is not None and target_rent is not None:
        raise ValueError("give a target deposit or a target rent, not both")
    equivalent = deposit + rent * divisor
    result: dict = {"deposit": deposit, "rent": rent, "rahn_equivalent": equivalent, "divisor": divisor}
    if target_deposit is None and target_rent is None:
        result["rent_if_deposit_is_zero"] = equivalent // divisor
        result["deposit_if_rent_is_zero"] = equivalent
        return result
    if target_deposit is not None:
        if target_deposit < 0:
            raise ValueError("target deposit cannot be negative")
        result["deposit"] = target_deposit
        result["rent"] = max(equivalent - target_deposit, 0) // divisor
    else:
        if target_rent < 0:
            raise ValueError("target rent cannot be negative")
        result["rent"] = target_rent
        result["deposit"] = max(equivalent - target_rent * divisor, 0)
    return result


def commission(deal_type: str, price: int | None = None, deposit: int | None = None, rent: int | None = None) -> dict:
    """The office's fee for a closed deal, in the shape an advisor can quote on the call."""
    if deal_type not in {"sale", "rent"}:
        raise ValueError("deal_type must be sale or rent")
    if deal_type == "sale":
        if not price or price <= 0:
            raise ValueError("price is required for a sale commission")
        total = round(price * COMMISSION_RATE_SALE)
        return {"deal_type": "sale", "rate": COMMISSION_RATE_SALE, "total": total, "per_side": total // 2}
    if (deposit or 0) < 0 or (rent or 0) < 0:
        raise ValueError("amounts cannot be negative")
    if not rent:
        raise ValueError("rent is required for a rental commission")
    total = round(rent * COMMISSION_RATE_RENT) * 2  # both sides pay
    return {"deal_type": "rent", "rate": COMMISSION_RATE_RENT, "total": total, "per_side": total // 2}


def suspicious_prices(listings, tenant_id: str, discount: float = SUSPICIOUS_DISCOUNT,
                      minimum_peers: int = 2) -> list[dict]:
    """فایلs priced far under their peers: a typo, a stale price, or bait for callers."""
    scoped = [listing for listing in listings if listing.tenant_id == tenant_id]
    findings = []
    for listing in scoped:
        peers = [
            other.price for other in scoped
            if other.id != listing.id and other.neighborhood == listing.neighborhood
            and other.deal_type == listing.deal_type and (other.price or 0) > 0
        ]
        # یک آگهی whose sale price is lower than its own deposit is almost never real.
        if listing.price and listing.deposit and listing.price < listing.deposit:
            findings.append({"listing": listing, "reason": "sale price below its own deposit",
                             "market_average": int(mean(peers)) if peers else None})
            continue
        if len(peers) < minimum_peers or not listing.price:
            continue
        average = mean(peers)
        if listing.price < average * discount:
            findings.append({
                "listing": listing, "reason": "price far below neighbourhood peers",
                "market_average": int(average), "discount_percent": round((1 - listing.price / average) * 100, 1),
            })
    return findings


def listing_matches(listing, criteria: dict) -> bool:
    if criteria.get("deal_type") and criteria["deal_type"] != listing.deal_type:
        return False
    if criteria.get("neighborhood") and criteria["neighborhood"] != listing.neighborhood:
        return False
    if criteria.get("bedrooms") is not None and criteria["bedrooms"] != listing.bedrooms:
        return False
    if criteria.get("max_price") is not None and (not listing.price or listing.price > criteria["max_price"]):
        return False
    if criteria.get("max_deposit") is not None and (not listing.deposit or listing.deposit > criteria["max_deposit"]):
        return False
    if criteria.get("max_rent") is not None and (not listing.rent or listing.rent > criteria["max_rent"]):
        return False
    return True


def saved_search_matches(search, listings) -> list:
    criteria = {
        "deal_type": search.deal_type, "neighborhood": search.neighborhood, "bedrooms": search.bedrooms,
        "max_price": search.max_price, "max_deposit": search.max_deposit, "max_rent": search.max_rent,
    }
    return [listing for listing in listings if listing.tenant_id == search.tenant_id and listing_matches(listing, criteria)]


def compare(listings) -> list[dict]:
    """The side-by-side rows Zillow now shows when a buyer has two homes on the shortlist."""
    return [{
        "id": listing.id,
        "title": listing.title,
        "neighborhood": listing.neighborhood,
        "deal_type": listing.deal_type,
        "bedrooms": listing.bedrooms,
        "area": listing.area,
        "price": listing.price,
        "deposit": listing.deposit,
        "rent": listing.rent,
        "price_per_meter": round(listing.price / listing.area) if listing.price and listing.area else None,
        "rent_per_meter": round(listing.rent / listing.area) if listing.rent and listing.area else None,
        "freshness": freshness_days(listing),
        "verified": listing.verified_at is not None,
    } for listing in listings]


def freshness_days(listing, now: datetime | None = None) -> int | None:
    touched = listing.updated_at or listing.created_at
    if touched is None:
        return None
    now = now or datetime.now(timezone.utc)
    return int((now - touched).total_seconds() // 86400)


def source_health(leads) -> dict:
    """Per-channel volume and unanswered rate, so a manager knows which feed is feeding the office."""
    by_channel: dict[str, dict] = {}
    for lead in leads:
        if not lead.messages:
            continue
        # A lead's channel is the one that first brought it in.
        channel = lead.messages[0].channel
        row = by_channel.setdefault(channel, {"channel": channel, "leads": 0, "unanswered": 0, "converted": 0})
        row["leads"] += 1
        if lead.state == "unanswered":
            row["unanswered"] += 1
        if lead.state == "converted":
            row["converted"] += 1
        last = lead.messages[-1].sent_at
        row["last_message_at"] = max(row["last_message_at"], last) if "last_message_at" in row else last
    rows = []
    for row in by_channel.values():
        row["unanswered_rate"] = round(row["unanswered"] / row["leads"], 3) if row["leads"] else 0.0
        row["conversion_rate"] = round(row["converted"] / row["leads"], 3) if row["leads"] else 0.0
        rows.append(row)
    return {"channels": sorted(rows, key=lambda row: -row["leads"])}


def viewing_reminders(viewings, agent_names: dict[str, str], lead_names: dict[str, str],
                      now: datetime | None = None, within_hours: int = 24) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    horizon = now + timedelta(hours=within_hours)
    due = [
        viewing for viewing in viewings
        if viewing.status == "scheduled" and now <= viewing.starts_at <= horizon
    ]
    return [{
        "id": viewing.id,
        "lead_id": viewing.lead_id,
        "lead_name": lead_names.get(viewing.lead_id),
        "listing_id": viewing.listing_id,
        "starts_at": viewing.starts_at,
        "agent_name": agent_names.get(viewing.agent_id) if viewing.agent_id else None,
    } for viewing in sorted(due, key=lambda item: item.starts_at)]


def followup_draft(lead, max_matches: int = 0, *_: object) -> str:
    """A Persian message an advisor can edit and send; it quotes only what the lead actually said."""
    intent = lead.intent
    name = (lead.name or "").split(" ")[0] if lead.name else ""
    parts = [f"{name + ' عزیز، ' if name else 'سلام، '}از پیام شما در «{lead.contact}» متوجه شدم که دنبال "]

    wants = []
    if intent.purpose == "buy":
        wants.append("خرید")
    elif intent.purpose == "rent":
        wants.append("اجاره")
    if intent.neighborhood:
        wants.append(f"در محلهٔ {intent.neighborhood}")
    if intent.price:
        wants.append(f"تا سقف {format_amount(intent.price)} تومان")
    if intent.deposit:
        wants.append(f"با رهن تا {format_amount(intent.deposit)} تومان")
    if intent.rent:
        wants.append(f"و اجارهٔ ماهانه تا {format_amount(intent.rent)} تومان")
    parts.append("، ".join(wants) if wants else "یک فایل ملکی")
    if max_matches:
        parts.append(f" هستید. همین حالا {format_count(max_matches)} فایل مناسب داریم")
    if intent.urgency == "high":
        parts.append(". چون فرمودید عجله دارید، امروز می‌توانم چند گزینه را برایتان بفرستم")
    parts.append(". اگر بخواهید، فایل‌ها را می‌فرستم؟")
    return "".join(parts)


PERSIAN_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def format_count(value: int) -> str:
    words = {1: "یک", 2: "دو", 3: "سه", 4: "چهار", 5: "پنج"}
    return words.get(value, str(value).translate(PERSIAN_DIGITS))


def format_amount(value: int | float) -> str:
    """Amounts are written the way an advisor reads them aloud: ۸ میلیارد, ۴۵۰ میلیون."""
    value = int(value)
    if value >= 1_000_000_000:
        text = f"{value / 1_000_000_000:g} میلیارد"
    elif value >= 1_000_000:
        text = f"{value / 1_000_000:g} میلیون"
    else:
        text = f"{value:,}"
    return text.translate(PERSIAN_DIGITS)
