import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hoshyar.api import HoshyarApi
from hoshyar.store import SqliteStore


class HoshyarApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.store = SqliteStore(Path(self.temp.name) / "hoshyar.sqlite3")
        self.api = HoshyarApi(self.store, bootstrap_key="bootstrap-secret")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def request(self, method: str, path: str, payload: dict | None = None, headers: dict | None = None):
        return self.api.handle(method, path, headers or {}, json.dumps(payload or {}).encode())

    def create_tenant(self) -> tuple[str, str]:
        status, response = self.request(
            "POST", "/v1/tenants", {"name": "املاک آفتاب"}, {"x-bootstrap-key": "bootstrap-secret"}
        )
        self.assertEqual(status, 201)
        return response["tenant"]["id"], response["api_key"]

    def test_health_does_not_require_authentication(self) -> None:
        self.assertEqual(self.request("GET", "/health")[0], 200)

    def test_tenant_creation_requires_bootstrap_key(self) -> None:
        self.assertEqual(self.request("POST", "/v1/tenants", {"name": "دفتر"})[0], 401)

    def test_authorized_office_can_ingest_messages_and_read_dashboard(self) -> None:
        tenant_id, api_key = self.create_tenant()
        headers = {"x-api-key": api_key}
        status, response = self.request(
            "POST", f"/v1/tenants/{tenant_id}/messages",
            {"contact": "09120000000", "body": "برای خرید فوری در پونک تا ۸ میلیارد", "channel": "telegram"}, headers,
        )
        self.assertEqual(status, 201)
        self.assertEqual(response["lead"]["intent"]["purpose"], "buy")
        status, dashboard = self.request("GET", f"/v1/tenants/{tenant_id}/dashboard", headers=headers)
        self.assertEqual(status, 200)
        self.assertEqual(dashboard["active_lead_count"], 1)

    def test_api_data_persists_after_api_is_recreated(self) -> None:
        tenant_id, api_key = self.create_tenant()
        headers = {"x-api-key": api_key}
        self.request(
            "POST", f"/v1/tenants/{tenant_id}/listings",
            {"title": "دوخوابه", "neighborhood": "پونک", "price": 7_000_000_000, "bedrooms": 2}, headers,
        )
        restored = HoshyarApi(self.store, bootstrap_key="bootstrap-secret")
        status, response = restored.handle("GET", f"/v1/tenants/{tenant_id}/dashboard", headers)
        self.assertEqual(status, 200)
        self.assertEqual(response["active_lead_count"], 0)

    def test_tenant_cannot_access_another_tenant(self) -> None:
        first_id, first_key = self.create_tenant()
        second_id, _ = self.create_tenant()
        status, _ = self.request("GET", f"/v1/tenants/{second_id}/dashboard", headers={"x-api-key": first_key})
        self.assertEqual(status, 401)
        self.assertNotEqual(first_id, second_id)


if __name__ == "__main__":
    unittest.main()
