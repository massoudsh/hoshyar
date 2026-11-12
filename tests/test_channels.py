from datetime import datetime, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hoshyar.api import HoshyarApi
from hoshyar.channels import ChannelPayloadError, normalize
from hoshyar.store import SqliteStore


class NormalizeTests(unittest.TestCase):
    def test_telegram_update_maps_sender_and_unix_date(self) -> None:
        message = normalize("telegram", {
            "message": {
                "message_id": 77, "date": 1_760_000_000, "chat_id": "555",
                "from": {"id": 9, "first_name": "مینا", "last_name": "ک"},
                "text": "برای خرید در پونک تا ۸ میلیارد",
            }
        })
        self.assertEqual(message["contact"], "555")
        self.assertEqual(message["name"], "مینا ک")
        self.assertEqual(message["external_id"], "77")
        self.assertEqual(message["sent_at"], datetime.fromtimestamp(1_760_000_000, tz=timezone.utc))

    def test_whatsapp_cloud_payload_and_millisecond_timestamp(self) -> None:
        message = normalize("whatsapp", {
            "message": {"from": "989120000000", "id": "wamid.1", "text": "اجاره در ونک"},
            "name": "سارا", "timestamp": 1_760_000_000_000,
        })
        self.assertEqual(message["contact"], "989120000000")
        self.assertEqual(message["body"], "اجاره در ونک")
        self.assertEqual(message["sent_at"].year, 2025)

    def test_marketplace_payload_uses_iso_time(self) -> None:
        message = normalize("divar", {"contact": "0912", "body": "فایل دارید؟", "sent_at": "2026-10-06T12:00:00Z"})
        self.assertEqual(message["sent_at"], datetime(2026, 10, 6, 12, tzinfo=timezone.utc))

    def test_missing_contact_or_body_is_rejected(self) -> None:
        with self.assertRaisesRegex(ChannelPayloadError, "contact"):
            normalize("sms", {"body": "سلام"})
        with self.assertRaisesRegex(ChannelPayloadError, "body"):
            normalize("sms", {"contact": "0912"})
        with self.assertRaisesRegex(ChannelPayloadError, "channel"):
            normalize("fax", {"contact": "1", "body": "x"})


class ChannelWebhookTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.store = SqliteStore(Path(self.temp.name) / "hoshyar.sqlite3")
        self.api = HoshyarApi(self.store, bootstrap_key="bootstrap-secret")
        status, response = self.api.handle(
            "POST", "/v1/tenants", {"x-bootstrap-key": "bootstrap-secret"}, json.dumps({"name": "دفتر"}).encode()
        )
        self.assertEqual(status, 201)
        self.tenant_id = response["tenant"]["id"]
        self.manager = {"x-api-key": response["api_key"]}

    def tearDown(self) -> None:
        self.temp.cleanup()

    def call(self, method: str, path: str, payload: dict | None = None, headers: dict | None = None):
        return self.api.handle(method, path, headers or {}, json.dumps(payload or {}).encode())

    def issue(self, channel: str) -> str:
        status, response = self.call("POST", f"/v1/tenants/{self.tenant_id}/channels/{channel}", headers=self.manager)
        self.assertEqual(status, 201)
        return response["secret"]

    def test_webhook_creates_a_lead_with_extracted_intent(self) -> None:
        secret = self.issue("telegram")
        status, response = self.call(
            "POST", f"/v1/channels/{self.tenant_id}/telegram",
            {"message": {"message_id": 1, "chat_id": "555", "text": "خرید فوری در پونک تا ۸ میلیارد"}},
            {"x-channel-secret": secret},
        )
        self.assertEqual(status, 201)
        _, workspace = self.call("GET", f"/v1/tenants/{self.tenant_id}/workspace", headers=self.manager)
        lead = workspace["leads"][0]
        self.assertEqual(lead["id"], response["lead_id"])
        self.assertEqual(lead["intent"]["purpose"], "buy")
        self.assertEqual(lead["messages"][0]["channel"], "telegram")

    def test_redelivered_message_is_not_stored_twice(self) -> None:
        secret = self.issue("whatsapp")
        payload = {"message": {"from": "98912", "id": "wamid.9", "text": "اجاره در ونک"}}
        first = self.call("POST", f"/v1/channels/{self.tenant_id}/whatsapp", payload, {"x-channel-secret": secret})
        second = self.call("POST", f"/v1/channels/{self.tenant_id}/whatsapp", payload, {"x-channel-secret": secret})
        self.assertEqual(first[0], 201)
        self.assertEqual(second[0], 200)
        self.assertTrue(second[1]["duplicate"])
        self.assertEqual(first[1]["lead_id"], second[1]["lead_id"])
        _, workspace = self.call("GET", f"/v1/tenants/{self.tenant_id}/workspace", headers=self.manager)
        self.assertEqual(len(workspace["leads"][0]["messages"]), 1)

    def test_webhook_requires_the_channel_secret(self) -> None:
        self.issue("sms")
        path = f"/v1/channels/{self.tenant_id}/sms"
        self.assertEqual(self.call("POST", path, {"contact": "1", "body": "x"}, {"x-channel-secret": "wrong"})[0], 401)
        self.assertEqual(self.call("POST", path, {"contact": "1", "body": "x"})[0], 401)
        other = self.issue("divar")
        self.assertEqual(self.call("POST", path, {"contact": "1", "body": "x"}, {"x-channel-secret": other})[0], 401)

    def test_unknown_channel_cannot_be_issued(self) -> None:
        status, _ = self.call("POST", f"/v1/tenants/{self.tenant_id}/channels/fax", headers=self.manager)
        self.assertEqual(status, 400)

    def test_agent_role_cannot_issue_a_channel_secret(self) -> None:
        self.call("POST", f"/v1/tenants/{self.tenant_id}/agents", {"name": "سارا"}, self.manager)
        _, session = self.call("POST", "/v1/sessions", {"tenant": self.tenant_id, "name": "سارا"})
        status, _ = self.call(
            "POST", f"/v1/tenants/{self.tenant_id}/channels/telegram", headers={"x-session-token": session["token"]}
        )
        self.assertEqual(status, 401)


if __name__ == "__main__":
    unittest.main()
