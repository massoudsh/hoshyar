from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

# Each channel posts its own shape; normalize it here so the domain only sees one message form.
CHANNELS = ("telegram", "whatsapp", "divar", "sheypoor", "sms")


class ChannelPayloadError(ValueError):
    pass


def _text(payload: dict[str, Any], *names: str) -> str | None:
    for name in names:
        value = payload.get(name)
        # Telegram and WhatsApp send chat and message ids as integers.
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            return str(value)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _sent_at(payload: dict[str, Any]) -> datetime:
    raw = payload.get("sent_at") or payload.get("timestamp")
    if raw is None:
        return datetime.now(timezone.utc)
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        # Telegram and WhatsApp send Unix seconds; anything past 10^11 is milliseconds.
        seconds = raw / 1000 if raw > 100_000_000_000 else raw
        return datetime.fromtimestamp(seconds, tz=timezone.utc)
    if isinstance(raw, str):
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError as error:
            raise ChannelPayloadError("sent_at must be ISO 8601 or Unix seconds") from error
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    raise ChannelPayloadError("sent_at must be ISO 8601 or Unix seconds")


def normalize(channel: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Map a channel webhook body onto contact/body/name/sent_at/external_id."""
    if channel not in CHANNELS:
        raise ChannelPayloadError(f"channel must be one of {', '.join(CHANNELS)}")
    if channel == "telegram":
        message = payload.get("message") if isinstance(payload.get("message"), dict) else payload
        sender = message.get("from") if isinstance(message.get("from"), dict) else {}
        contact = _text(message, "chat_id") or _text(sender, "id")
        body = _text(message, "text")
        name = " ".join(part for part in (sender.get("first_name"), sender.get("last_name")) if part) or None
        external_id = _text(message, "message_id")
        sent_at = _sent_at({"timestamp": message.get("date")} if message.get("date") else payload)
    elif channel == "whatsapp":
        message = payload.get("message") if isinstance(payload.get("message"), dict) else payload
        contact = _text(message, "from", "wa_id", "contact")
        body = _text(message, "text", "body")
        name = _text(payload, "name", "profile_name")
        external_id = _text(message, "id")
        sent_at = _sent_at(payload)
    else:
        contact = _text(payload, "contact", "phone", "sender")
        body = _text(payload, "body", "text", "message")
        name = _text(payload, "name")
        external_id = _text(payload, "id", "external_id")
        sent_at = _sent_at(payload)
    if not contact:
        raise ChannelPayloadError("contact is required")
    if not body:
        raise ChannelPayloadError("body is required")
    return {
        "contact": contact,
        "body": body,
        "name": name,
        "sent_at": sent_at,
        "external_id": external_id,
    }
