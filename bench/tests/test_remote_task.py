import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from ssebench.tasks.manifest import Manifest
from ssebench.tasks.remote import RemoteTask

# This checkout: bench/tests/ is two levels below the repository root.
CHECKOUT = Path(__file__).resolve().parents[2]
TASK = "gjson-196-bf4efcb"


@pytest.fixture
def catalog() -> Iterator[str]:
    """A catalog server that knows one pilot task, as `ssebench-catalog serve` returns it."""
    manifest = Manifest.model_validate_json((CHECKOUT / "datasets" / "pilot" / "manifest.json").read_text())
    entry = next(t for t in manifest.tasks if t.id == TASK).model_dump(mode="json")
    entry["image"] = f"registry.test/{entry['image']}"
    body = json.dumps(entry).encode()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path != f"/tasks/{TASK}":
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            _ = self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}/"
    server.shutdown()
    server.server_close()


def test_remote_task(catalog: str) -> None:
    task = RemoteTask(TASK, catalog)

    assert task.docker_image_name == f"registry.test/case/pilot/{TASK}"
    assert task.get_task_metadata().id == TASK
    assert task.get_task_metadata().source == "/src/gjson"


def test_unknown_remote_task(catalog: str) -> None:
    with pytest.raises(LookupError, match="not in the catalog"):
        _ = RemoteTask("missing", catalog)
