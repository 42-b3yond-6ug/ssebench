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
    """
    Daemon wrapper, this connect with the daemon.sock
    """

    def __init__(self):
        if (sock := os.getenv("SSE_DAEMON_SOCKET")) is not None:
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
        return self.post("/prepare_grading", {})

    def version(self):
        return self.get("/version")

    def project(self):
        return self.get("/project")

    def capabilities(self):
        return self.get("/capabilities")

    def tool(self, name, action, data):
        return self.post(
            f"/tool/{name}?action={action}",
            data,
            {"Content-Type": "application/json"},
        )
