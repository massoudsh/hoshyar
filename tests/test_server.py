import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import unittest

from hoshyar.server import create_server


class HttpServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.server = create_server(Path(self.temp.name) / "hoshyar.sqlite3", "bootstrap-secret", port=0)
        self.thread = Thread(target=self.server.serve_forever)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()
        self.temp.cleanup()

    def request(self, method: str, path: str, payload: dict | None = None, headers: dict | None = None):
        request = Request(
            self.base_url + path, method=method,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers={"Content-Type": "application/json", **(headers or {})},
        )
        with urlopen(request, timeout=5) as response:
            return response.status, response.headers, response.read()

    def test_health_endpoint_is_served_over_http(self) -> None:
        with urlopen(f"{self.base_url}/health", timeout=5) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(json.loads(response.read()), {"status": "ok"})

    def test_frontend_assets_are_served(self) -> None:
        for path, content_type in (("/", "text/html"), ("/styles.css", "text/css"), ("/app.js", "text/javascript")):
            status, headers, body = self.request("GET", path)
            self.assertEqual(status, 200)
            self.assertIn(content_type, headers["Content-Type"])
            self.assertTrue(body)

    def test_office_workspace_round_trip_over_http(self) -> None:
        _, _, body = self.request("POST", "/v1/tenants", {"name": "دفتر"}, {"X-Bootstrap-Key": "bootstrap-secret"})
        tenant = json.loads(body)
        headers = {"X-API-Key": tenant["api_key"]}
        status, _, _ = self.request(
            "POST", f"/v1/tenants/{tenant['tenant']['id']}/messages",
            {"contact": "0912", "body": "خرید در پونک", "channel": "manual"}, headers,
        )
        self.assertEqual(status, 201)
        status, _, body = self.request("GET", f"/v1/tenants/{tenant['tenant']['id']}/workspace", headers=headers)
        self.assertEqual(status, 200)
        self.assertEqual(len(json.loads(body)["leads"]), 1)

    def test_workspace_rejects_wrong_key(self) -> None:
        _, _, body = self.request("POST", "/v1/tenants", {"name": "دفتر"}, {"X-Bootstrap-Key": "bootstrap-secret"})
        tenant_id = json.loads(body)["tenant"]["id"]
        with self.assertRaises(HTTPError) as raised:
            self.request("GET", f"/v1/tenants/{tenant_id}/workspace", headers={"X-API-Key": "wrong"})
        self.assertEqual(raised.exception.code, 401)


if __name__ == "__main__":
    unittest.main()
