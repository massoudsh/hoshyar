from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import time
from uuid import uuid4

from .api import HoshyarApi
from .store import SqliteStore
from .telemetry import configure, get_logger, request_id


def create_server(database_path: str | Path, bootstrap_key: str, host: str = "127.0.0.1", port: int = 8000) -> ThreadingHTTPServer:
    api = HoshyarApi(SqliteStore(database_path), bootstrap_key)
    log = get_logger()

    class RequestHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            assets = {"/": ("index.html", "text/html; charset=utf-8"),
                      "/styles.css": ("styles.css", "text/css; charset=utf-8"),
                      "/app.js": ("app.js", "text/javascript; charset=utf-8")}
            if self.path in assets:
                filename, content_type = assets[self.path]
                content = (Path(__file__).resolve().parent.parent / "frontend" / filename).read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(content)))
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(content)
                return
            self._respond()

        def do_POST(self) -> None:
            self._respond()

        def do_DELETE(self) -> None:
            self._respond()

        def do_PATCH(self) -> None:
            self._respond()

        def _respond(self) -> None:
            token = request_id.set(uuid4().hex[:16])
            started = time.monotonic()
            try:
                self._dispatch()
            finally:
                elapsed_ms = round((time.monotonic() - started) * 1000, 1)
                log.info(
                    "request",
                    extra={
                        "method": self.command,
                        "path": self.path,
                        "status": getattr(self, "_status", None),
                        "duration_ms": elapsed_ms,
                    },
                )
                request_id.reset(token)

        def _dispatch(self) -> None:
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                self._send(400, {"error": "invalid content length"})
                return
            if length < 0 or self.headers.get("Transfer-Encoding"):
                self._send(400, {"error": "unsupported request framing"})
                return
            if length > 1_000_000:
                self._send(413, {"error": "request body is too large"})
                return
            body = self.rfile.read(length)
            headers = {key.lower(): value for key, value in self.headers.items()}
            status, payload = api.handle(self.command, self.path, headers, body)
            self._send(status, payload)

        def _send(self, status: int, payload: dict) -> None:
            self._status = status
            encoded = json.dumps(payload, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, format: str, *args: object) -> None:
            return

    return ThreadingHTTPServer((host, port), RequestHandler)


def main() -> None:
    log = configure(os.environ.get("HOSHYAR_LOG_LEVEL", "info"))
    bootstrap_key = os.environ.get("HOSHYAR_BOOTSTRAP_KEY")
    if not bootstrap_key:
        raise SystemExit("HOSHYAR_BOOTSTRAP_KEY must be set")
    database_path = os.environ.get("HOSHYAR_DATABASE_PATH", "hoshyar.sqlite3")
    host = os.environ.get("HOSHYAR_HOST", "127.0.0.1")
    port = int(os.environ.get("HOSHYAR_PORT", "8000"))
    server = create_server(database_path, bootstrap_key, host=host, port=port)
    log.info("server started", extra={"host": host, "port": server.server_port, "database": str(database_path)})
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("server stopped")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
