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

    def sign_in(self, tenant_id: str, name: str) -> dict:
        status, response = self.request("POST", "/v1/sessions", {"tenant": tenant_id, "name": name})
        self.assertEqual(status, 201)
        return {"x-session-token": response["token"]}

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

    def test_workspace_lists_leads_and_assigns_an_agent(self) -> None:
        tenant_id, api_key = self.create_tenant()
        headers = {"x-api-key": api_key}
        _, agent = self.request("POST", f"/v1/tenants/{tenant_id}/agents", {"name": "سارا"}, headers)
        _, lead_response = self.request(
            "POST", f"/v1/tenants/{tenant_id}/messages",
            {"contact": "0912", "body": "خرید در پونک", "channel": "manual"}, headers,
        )
        lead_id = lead_response["lead"]["id"]
        status, workspace = self.request("GET", f"/v1/tenants/{tenant_id}/workspace", headers=headers)
        self.assertEqual(status, 200)
        self.assertEqual(len(workspace["leads"]), 1)
        self.assertEqual(workspace["tenant"]["id"], tenant_id)

        status, _ = self.request(
            "POST", f"/v1/tenants/{tenant_id}/leads/{lead_id}/assignment", {"agent_id": agent["agent"]["id"]}, headers
        )
        self.assertEqual(status, 200)
        _, workspace = self.request("GET", f"/v1/tenants/{tenant_id}/workspace", headers=headers)
        self.assertEqual(workspace["leads"][0]["assigned_agent_id"], agent["agent"]["id"])

    def test_member_login_scopes_an_agent_to_their_own_leads(self) -> None:
        tenant_id, api_key = self.create_tenant()
        headers = {"x-api-key": api_key}
        self.request("POST", f"/v1/tenants/{tenant_id}/agents", {"name": "سارا", "role": "manager"}, headers)
        _, sara = self.request("POST", f"/v1/tenants/{tenant_id}/agents", {"name": "سارا رضایی"}, headers)
        agent_headers = self.sign_in(tenant_id, "سارا رضایی")

        self.request("POST", f"/v1/tenants/{tenant_id}/messages", {"contact": "0911", "body": "خرید", "channel": "manual"}, headers)
        _, own = self.request(
            "POST", f"/v1/tenants/{tenant_id}/messages",
            {"contact": "0912", "body": "اجاره", "channel": "manual", "agent_id": sara["agent"]["id"]}, headers,
        )
        self.assertIsNotNone(own["lead"]["assigned_agent_id"])

        status, workspace = self.request("GET", f"/v1/tenants/{tenant_id}/workspace", headers=agent_headers)
        self.assertEqual(status, 200)
        self.assertEqual(workspace["viewer"]["role"], "agent")
        self.assertEqual([lead["contact"] for lead in workspace["leads"]], ["0912"])
        self.assertEqual({item["lead"]["contact"] for item in workspace["followups"]}, {"0912"})

    def test_agent_role_cannot_manage_the_office(self) -> None:
        tenant_id, api_key = self.create_tenant()
        self.request("POST", f"/v1/tenants/{tenant_id}/agents", {"name": "علی"}, {"x-api-key": api_key})
        agent_headers = self.sign_in(tenant_id, "علی")
        for path, payload in (
            (f"/v1/tenants/{tenant_id}/agents", {"name": "دستیار"}),
            (f"/v1/tenants/{tenant_id}/listings", {"title": "ف", "neighborhood": "ونک", "bedrooms": 1, "price": 1_000}),
        ):
            status, _ = self.request("POST", path, payload, agent_headers)
            self.assertEqual(status, 401)
        status, _ = self.request("GET", f"/v1/tenants/{tenant_id}/workspace", headers={"x-session-token": "forged"})
        self.assertEqual(status, 401)

    def test_login_rejects_unknown_and_ambiguous_names(self) -> None:
        tenant_id, api_key = self.create_tenant()
        self.assertEqual(self.request("POST", "/v1/sessions", {"tenant": tenant_id, "name": "ناشناس"})[0], 401)
        self.request("POST", f"/v1/tenants/{tenant_id}/agents", {"name": "سارا"}, {"x-api-key": api_key})
        self.request("POST", f"/v1/tenants/{tenant_id}/agents", {"name": "سارا"}, {"x-api-key": api_key})
        self.assertEqual(self.request("POST", "/v1/sessions", {"tenant": tenant_id, "name": "سارا"})[0], 400)

    def test_listing_patch_and_delete_round_trip(self) -> None:
        tenant_id, api_key = self.create_tenant()
        headers = {"x-api-key": api_key}
        _, created = self.request(
            "POST", f"/v1/tenants/{tenant_id}/listings",
            {"title": "ونک", "neighborhood": "ونک", "bedrooms": 2, "price": 5_000_000_000}, headers,
        )
        listing_id = created["listing"]["id"]
        status, patched = self.request(
            "PATCH", f"/v1/tenants/{tenant_id}/listings/{listing_id}", {"price": 4_000_000_000}, headers
        )
        self.assertEqual(status, 200)
        self.assertEqual(patched["listing"]["price"], 4_000_000_000)
        self.assertEqual(patched["listing"]["title"], "ونک")
        self.assertEqual(self.request("PATCH", f"/v1/tenants/{tenant_id}/listings/{listing_id}", {}, headers)[0], 400)
        self.assertEqual(self.request("DELETE", f"/v1/tenants/{tenant_id}/listings/{listing_id}", headers=headers)[0], 200)
        _, workspace = self.request("GET", f"/v1/tenants/{tenant_id}/workspace", headers=headers)
        self.assertEqual(workspace["listings"], [])

    def test_member_with_a_password_must_supply_it_and_it_is_never_returned(self) -> None:
        tenant_id, api_key = self.create_tenant()
        headers = {"x-api-key": api_key}
        status, created = self.request(
            "POST", f"/v1/tenants/{tenant_id}/agents", {"name": "سارا", "password": "correct-horse"}, headers
        )
        self.assertEqual(status, 201)
        self.assertNotIn("password_hash", created["agent"])
        _, workspace = self.request("GET", f"/v1/tenants/{tenant_id}/workspace", headers=headers)
        self.assertNotIn("password_hash", workspace["agents"][0])

        self.assertEqual(self.request("POST", "/v1/sessions", {"tenant": tenant_id, "name": "سارا"})[0], 401)
        self.assertEqual(
            self.request("POST", "/v1/sessions", {"tenant": tenant_id, "name": "سارا", "password": "wrong"})[0], 401
        )
        status, session = self.request(
            "POST", "/v1/sessions", {"tenant": tenant_id, "name": "سارا", "password": "correct-horse"}
        )
        self.assertEqual(status, 201)
        self.assertEqual(session["member"]["role"], "agent")

    def test_short_password_is_rejected_and_manager_can_reset_it(self) -> None:
        tenant_id, api_key = self.create_tenant()
        headers = {"x-api-key": api_key}
        self.assertEqual(
            self.request("POST", f"/v1/tenants/{tenant_id}/agents", {"name": "علی", "password": "short"}, headers)[0], 400
        )
        _, created = self.request("POST", f"/v1/tenants/{tenant_id}/agents", {"name": "علی"}, headers)
        agent_id = created["agent"]["id"]
        self.assertEqual(
            self.request("POST", f"/v1/tenants/{tenant_id}/agents/{agent_id}/password", {"password": "new-secret-1"}, headers)[0],
            200,
        )
        self.assertEqual(
            self.request("POST", "/v1/sessions", {"tenant": tenant_id, "name": "علی", "password": "new-secret-1"})[0], 201
        )

    def test_performance_report_accepts_a_date_range(self) -> None:
        tenant_id, api_key = self.create_tenant()
        headers = {"x-api-key": api_key}
        _, agent = self.request("POST", f"/v1/tenants/{tenant_id}/agents", {"name": "سارا"}, headers)
        self.request(
            "POST", f"/v1/tenants/{tenant_id}/messages",
            {"contact": "0911", "body": "خرید", "channel": "manual"}, headers,
        )
        self.request(
            "POST", f"/v1/tenants/{tenant_id}/messages",
            {"contact": "0911", "body": "پاسخ", "channel": "manual", "direction": "outbound",
             "agent_id": agent["agent"]["id"]}, headers,
        )
        status, report = self.request("GET", f"/v1/tenants/{tenant_id}/performance", headers=headers)
        self.assertEqual(status, 200)
        self.assertEqual(report["office"]["replies"], 1)
        self.assertEqual(report["agents"][0]["agent"]["name"], "سارا")
        self.assertIsNotNone(report["agents"][0]["response_hours"])

        status, _ = self.request(
            "GET", f"/v1/tenants/{tenant_id}/performance?since=2026-10-01T00:00:00Z&until=2026-10-02T00:00:00Z",
            headers=headers,
        )
        self.assertEqual(status, 200)
        self.assertEqual(
            self.request("GET", f"/v1/tenants/{tenant_id}/performance?since=not-a-date", headers=headers)[0], 400
        )

    def test_workspace_requires_the_tenant_key(self) -> None:
        tenant_id, _ = self.create_tenant()
        _, other_key = self.create_tenant()
        status, _ = self.request("GET", f"/v1/tenants/{tenant_id}/workspace", headers={"x-api-key": other_key})
        self.assertEqual(status, 401)

    def test_tenant_cannot_access_another_tenant(self) -> None:
        first_id, first_key = self.create_tenant()
        second_id, _ = self.create_tenant()
        status, _ = self.request("GET", f"/v1/tenants/{second_id}/dashboard", headers={"x-api-key": first_key})
        self.assertEqual(status, 401)
        self.assertNotEqual(first_id, second_id)


if __name__ == "__main__":
    unittest.main()
