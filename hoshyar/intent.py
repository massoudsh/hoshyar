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
_SELL = ("بفروشم", "می‌فروشم", "میفروشم", "فروش ملک", "برای فروش دارم", "برای فروش", "قصد فروش")
_URGENT = ("فوری", "ضروری", "امروز", "همین الان", "هرچه سریع‌تر", "اسباب‌کشی")

_UNIT = {"میلیارد": 1_000_000_000, "میلیون": 1_000_000, "هزار": 1_000}
_AMOUNT = re.compile(r"(?P<number>\d+(?:\.\d+)?)\s*(?P<unit>میلیارد|میلیون|هزار)?")
_LABEL = re.compile(r"(?P<word>رهن|ودیعه|پیش‌پرداخت|اجاره‌بها|اجاره)")
_DEPOSIT_WORDS = frozenset({"رهن", "ودیعه", "پیش‌پرداخت"})


def _normalize(text: str) -> str:
    return text.translate(_DIGITS).replace("ي", "ی").replace("ك", "ک").replace("\u200c", "‌")


def _amount(match: re.Match[str]) -> int | None:
    unit = match.group("unit")
    if not unit:
        return None
    return int(float(match.group("number")) * _UNIT[unit])


def _label(word: str) -> str:
    return "deposit" if word in _DEPOSIT_WORDS else "rent"


_QUALIFIERS = frozenset({"کامل", "کل", "جمعا", "جمعاً", "حدود", "تا", "توی", "در"})


def _is_adjacent(gap: str) -> bool:
    """Allow only light joining text between an amount and its keyword.

    A comma separates two clauses and carries no label, so "۲۰ میلیون، رهن ۳۰۰ میلیون"
    keeps its comma from binding "۲۰ میلیون" to the following "رهن". Short qualifiers such as
    "رهن کامل ۷۰۰ میلیون" still bind, because they never carry a competing amount label.
    """
    if any(character in gap for character in "،,؛;:"):
        return False
    words = [word for word in re.split(r"[\s\u200c-–]+", gap) if word]
    return len(words) <= 1 and (not words or words[0] in _QUALIFIERS)


def _rental_amounts(text: str) -> tuple[int | None, int | None]:
    """Pair each amount with the single keyword it belongs to.

    An amount is labelled by a keyword that sits immediately before it ("رهن ۳۰۰ میلیون") or
    immediately after it ("۳۰۰ میلیون رهن"). Consuming each keyword once keeps
    "۳۰۰ میلیون رهن و ۲۰ میلیون اجاره" from reading both amounts as the same term.
    """
    amounts = [(match, _amount(match)) for match in _AMOUNT.finditer(text)]
    amounts = [(match, value) for match, value in amounts if value is not None]
    keywords = [(match, _label(match.group("word"))) for match in _LABEL.finditer(text)]
    amount_starts = [match.start() for match, _ in amounts]

    def next_amount_start(position: int) -> int:
        return next((start for start in amount_starts if start >= position), len(text))

    deposit = rent = None
    used: set[int] = set()
    for amount_match, value in amounts:
        start, end = amount_match.span()
        limit = next_amount_start(end)
        trailing = next(
            ((index, keyword) for index, keyword in enumerate(keywords)
             if index not in used and keyword[0].start() >= end and keyword[0].end() <= limit
             and _is_adjacent(text[end:keyword[0].start()])),
            None,
        )
        leading = next(
            ((index, keyword) for index, keyword in reversed(list(enumerate(keywords)))
             if index not in used and keyword[0].end() <= start and _is_adjacent(text[keyword[0].end():start])),
            None,
        )
        # Prefer whichever adjacent keyword is closer; on a tie the keyword right before the amount wins.
        trailing_gap = trailing[1][0].start() - end if trailing else None
        leading_gap = start - leading[1][0].end() if leading else None
        if trailing and (leading is None or trailing_gap < leading_gap):
            chosen = trailing
        else:
            chosen = leading
        if chosen is None:
            continue
        index, (_, kind) = chosen
        used.add(index)
        if kind == "deposit" and deposit is None:
            deposit = value
        elif kind == "rent" and rent is None:
            rent = value
    return deposit, rent


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

    price = deposit = rent = None
    if purpose == "rent":
        deposit, rent = _rental_amounts(cleaned)
        if deposit or rent:
            signals += 1
    else:
        values = [value for match in _AMOUNT.finditer(cleaned) if (value := _amount(match)) is not None]
        price = max(values, default=None)
        if price:
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
        price=price,
        deposit=deposit,
        rent=rent,
        neighborhood=neighborhood,
        urgency=urgency,
        confidence=round(signals / 4, 2),
    )


def merge_intent(old: Intent, new: Intent) -> Intent:
    return Intent(
        purpose=new.purpose or old.purpose,
        price=new.price or old.price,
        deposit=new.deposit or old.deposit,
        rent=new.rent or old.rent,
        neighborhood=new.neighborhood or old.neighborhood,
        urgency=new.urgency or old.urgency,
        confidence=max(old.confidence, new.confidence),
    )
