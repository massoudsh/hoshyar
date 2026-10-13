import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.request import urlopen
import unittest

from hoshyar.server import create_server


class HttpServerTests(unittest.TestCase):
    def test_health_endpoint_is_served_over_http(self) -> None:
        with TemporaryDirectory() as directory:
            server = create_server(Path(directory) / "hoshyar.sqlite3", "bootstrap-secret", port=0)
            thread = Thread(target=server.serve_forever)
            thread.start()
            try:
                with urlopen(f"http://127.0.0.1:{server.server_port}/health") as response:
                    self.assertEqual(response.status, 200)
                    self.assertEqual(json.loads(response.read()), {"status": "ok"})
            finally:
                server.shutdown()
                thread.join()
                server.server_close()


if __name__ == "__main__":
    unittest.main()
