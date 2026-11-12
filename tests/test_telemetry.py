import io
import json
import logging
import unittest

from hoshyar.telemetry import JsonFormatter, configure, request_id


class JsonLoggingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.logger = configure("debug")
        self.stream = io.StringIO()
        self.handler = logging.StreamHandler(self.stream)
        self.handler.setFormatter(JsonFormatter())
        self.logger.addHandler(self.handler)

    def tearDown(self) -> None:
        self.logger.removeHandler(self.handler)

    def emitted(self) -> dict:
        return json.loads(self.stream.getvalue().strip().splitlines()[-1])

    def test_log_line_is_single_json_object_with_fields(self) -> None:
        self.logger.info("request", extra={"method": "GET", "status": 200, "duration_ms": 1.5})
        line = self.emitted()
        self.assertEqual(line["message"], "request")
        self.assertEqual(line["level"], "info")
        self.assertEqual(line["method"], "GET")
        self.assertEqual(line["status"], 200)
        self.assertEqual(line["duration_ms"], 1.5)
        self.assertIn("time", line)

    def test_request_id_is_attached_and_cleared(self) -> None:
        token = request_id.set("abc123")
        try:
            self.logger.info("inside")
        finally:
            request_id.reset(token)
        self.assertEqual(self.emitted()["request_id"], "abc123")

        self.logger.info("outside")
        self.assertNotIn("request_id", self.emitted())

    def test_configure_is_idempotent(self) -> None:
        first = len(self.logger.handlers)
        configure("warning")
        self.assertEqual(len(self.logger.handlers), first)
        self.assertEqual(self.logger.level, logging.WARNING)

    def test_persian_values_survive_serialization(self) -> None:
        self.logger.info("دفتر", extra={"tenant": "املاک آفتاب"})
        raw = self.stream.getvalue()
        self.assertIn("املاک آفتاب", raw)
        self.assertEqual(json.loads(raw)["tenant"], "املاک آفتاب")


if __name__ == "__main__":
    unittest.main()
