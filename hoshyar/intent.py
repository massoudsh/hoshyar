from __future__ import annotations

import re

from .models import Intent

_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

NEIGHBORHOODS = (
    "سعادت‌آباد", "سعادت آباد", "پونک", "نیاوران", "ونک", "جردن", "الهیه",
    "زعفرانیه", "شهرک غرب", "صادقیه", "تهرانپارس", "نارمک", "یوسف‌آباد",
    "یوسف آباد", "ستارخان", "میرداماد", "قیطریه", "اکباتان", "شهران", "دروس",
)

_BUY = ("خرید", "بخرم", "بخریم", "بخرمش", "میخرم", "می‌خرم", "فروشی")
_RENT = ("اجاره", "رهن", "اجاره‌ای", "رهن و اجاره")
_SELL = ("بفروشم", "می‌فروشم", "میفروشم", "فروش ملک", "برای فروش دارم")
_URGENT = ("فوری", "ضروری", "امروز", "همین الان", "هرچه سریع‌تر", "اسباب‌کشی")

_AMOUNT = re.compile(r"(\d+(?:\.\d+)?)\s*(میلیارد|میلیون|هزار)?\s*(?:تومان|تومن)?")


def _normalize(text: str) -> str:
    return text.translate(_DIGITS).replace("ي", "ی").replace("ك", "ک").replace("\u200c", "‌")


def _extract_budget(text: str) -> int | None:
    best: int | None = None
    for number, unit in _AMOUNT.findall(text):
        if not unit:
            continue
        multiplier = {"میلیارد": 1_000_000_000, "میلیون": 1_000_000, "هزار": 1_000}[unit]
        value = int(float(number) * multiplier)
        if best is None or value > best:
            best = value
    return best


def extract_intent(text: str) -> Intent:
    cleaned = _normalize(text)
    signals = 0

    purpose: str | None = None
    if any(word in cleaned for word in _SELL):
        purpose = "sell"
    elif any(word in cleaned for word in _RENT):
        purpose = "rent"
    elif any(word in cleaned for word in _BUY):
        purpose = "buy"
    if purpose:
        signals += 1

    budget = _extract_budget(cleaned)
    if budget:
        signals += 1

    neighborhood = next((n for n in NEIGHBORHOODS if n in cleaned), None)
    if neighborhood:
        signals += 1
        neighborhood = neighborhood.replace(" ", "‌") if neighborhood == "سعادت آباد" else neighborhood

    urgency = "high" if any(word in cleaned for word in _URGENT) else None
    if urgency:
        signals += 1

    return Intent(
        purpose=purpose,
        budget=budget,
        neighborhood=neighborhood,
        urgency=urgency,
        confidence=round(signals / 4, 2),
    )


def merge_intent(old: Intent, new: Intent) -> Intent:
    return Intent(
        purpose=new.purpose or old.purpose,
        budget=new.budget or old.budget,
        neighborhood=new.neighborhood or old.neighborhood,
        urgency=new.urgency or old.urgency,
        confidence=max(old.confidence, new.confidence),
    )
