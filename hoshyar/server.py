from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path

from .api import HoshyarApi
from .store import SqliteStore


def create_server(database_path: str | Path, bootstrap_key: str, host: str = "127.0.0.1", port: int = 8000) -> ThreadingHTTPServer:
    api = HoshyarApi(SqliteStore(database_path), bootstrap_key)

    class RequestHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self._respond()

        def do_POST(self) -> None:
            self._respond()

        def _respond(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 1_000_000:
                self._send(413, {"error": "request body is too large"})
                return
            body = self.rfile.read(length)
            headers = {key.lower(): value for key, value in self.headers.items()}
            status, payload = api.handle(self.command, self.path, headers, body)
            self._send(status, payload)

        def _send(self, status: int, payload: dict) -> None:
            encoded = json.dumps(payload, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, format: str, *args: object) -> None:
            return

    return ThreadingHTTPServer((host, port), RequestHandler)


def main() -> None:
    bootstrap_key = os.environ.get("HOSHYAR_BOOTSTRAP_KEY")
    if not bootstrap_key:
        raise SystemExit("HOSHYAR_BOOTSTRAP_KEY must be set")
    database_path = os.environ.get("HOSHYAR_DATABASE_PATH", "hoshyar.sqlite3")
    create_server(database_path, bootstrap_key).serve_forever()


if __name__ == "__main__":
    main()
