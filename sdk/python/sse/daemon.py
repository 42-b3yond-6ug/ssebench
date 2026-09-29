"""HTTP client of ``ssebench-daemon``, which the rest of the SDK goes through.

The client connects to the Unix socket in ``SSE_DAEMON_SOCKET``, or, when that is unset, over
TCP to the ``host:port`` in ``SSE_AGENT_DOCKER``. The daemon's HTTP API is described in
docs/reference/daemon-api.md.
"""

from __future__ import annotations

import logging
import os
import urllib.parse
from importlib.metadata import version

import requests
import requests_unixsocket
from packaging.version import InvalidVersion, Version

from sse.error import SDKError

__version__ = version("ssebench.sdk")

log = logging.getLogger(__name__)


def same_version(sdk_version: str, daemon_version: object) -> bool:
    """Compare the SDK's PEP 440 version with the daemon's SemVer one.

    Both come from the same release, spelled per ecosystem (1.0.0rc1 and
    1.0.0-rc.1); PEP 440 parsing normalizes the SemVer spelling.
    """
    try:
        return Version(str(daemon_version)) == Version(sdk_version)
    except InvalidVersion:
        return False


class Daemon:
    """A connection to the daemon.

    Creating one asks the daemon for its version and logs a warning when it differs from the
    SDK's. It connects to ``socket`` when given, else to ``SSE_DAEMON_SOCKET``, else to the
    daemon at ``SSE_AGENT_DOCKER``. Raises ``Exception`` when there is none of them, and
    ``RuntimeError`` when the daemon does not answer.
    """

    def __init__(self, socket: str | None = None):
        if (sock := socket or os.getenv("SSE_DAEMON_SOCKET")) is not None:
            self.conn = requests_unixsocket.Session()
            self.base_url = "http+unix://" + urllib.parse.quote_plus(sock)
        elif os.getenv("SSE_AGENT_DOCKER") is not None:
            docker_host = os.getenv("SSE_AGENT_DOCKER")
            self.conn = requests.Session()
            self.base_url = f"http://{docker_host}"
        else:
            raise Exception("Cannot establish connection to daemon")

        # Version check: SDK and daemon should match
        self._check_version()

    def _check_version(self):
        """Check that SDK version matches daemon version."""
        try:
            response = self.conn.get(
                f"{self.base_url}/version", headers={"Connection": "close"}
            )
            data = response.json()
            daemon_version = data.get("version")
            if not same_version(__version__, daemon_version):
                log.warning(
                    "SDK version (%s) does not match daemon version (%s)",
                    __version__,
                    daemon_version,
                )
        except Exception as e:
            raise RuntimeError(f"Failed to verify daemon version: {e}") from e

    def get(self, path, headers=None):
        """Send ``GET path`` and return the JSON body.

        Raises :class:`~sse.error.SDKError` with the daemon's message when it answers with an
        error status, and on network errors.
        """
        merged_headers = {"Connection": "close"}
        if headers:
            merged_headers.update(headers)
        try:
            response = self.conn.get(f"{self.base_url}{path}", headers=merged_headers)
            data = response.json()
            if not response.ok:
                raise SDKError(data.get("error", "unknown error"))
            return data
        except SDKError:
            raise
        except Exception as e:
            raise SDKError(f"network error: {e}") from e

    def post(self, path, data, headers=None):
        """Send ``POST path`` with ``data`` as the JSON body and return the JSON body of the answer.

        Raises :class:`~sse.error.SDKError` as :meth:`get` does.
        """
        merged_headers = {"Connection": "close"}
        if headers:
            merged_headers.update(headers)
        try:
            response = self.conn.post(
                f"{self.base_url}{path}", json=data, headers=merged_headers
            )
            result = response.json()
            if not response.ok:
                raise SDKError(result.get("error", "unknown error"))
            return result
        except SDKError:
            raise
        except Exception as e:
            raise SDKError(f"network error: {e}") from e

    def prepare_grading(self):
        """``POST /prepare_grading``: save the agent's diff and apply it to the copy that is graded.

        Only the admin socket accepts it.
        """
        return self.post("/prepare_grading", {})

    def version(self):
        """``GET /version``: the daemon's version."""
        return self.get("/version")

    def project(self):
        """``GET /project``: the task's metadata, as :class:`sse.project.Metadata` holds it."""
        return self.get("/project")

    def capabilities(self):
        """``GET /capabilities``: the checks the task supports."""
        return self.get("/capabilities")

    def tool(self, name, action, data):
        """``POST /tool/{name}?action={action}`` with ``data`` as the JSON body."""
        return self.post(
            f"/tool/{name}?action={action}",
            data,
            {"Content-Type": "application/json"},
        )
