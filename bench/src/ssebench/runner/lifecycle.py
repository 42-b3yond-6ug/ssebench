"""How a run is identified from outside and how it ends when the CLI is asked to stop.

A tool that starts `ssebench run` labels the run with its own ID and finds the containers by it, rather
than by task, which several runs can share. The CLI also runs the container in the foreground, so a
SIGTERM to the CLI would otherwise end it with no summary, and no record of what the run spent.
"""

import logging
import os
import re
import signal
import subprocess
import tempfile
import time
from pathlib import Path
from types import FrameType, TracebackType

logger = logging.getLogger(__name__)

RUN_ID_LABEL = "ssebench.run-id"
"""Container label with the caller's `--run-id`."""
RUN_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")

STOP_GRACE_SECONDS = 20
"""How long `docker stop` waits for the entrypoint to clean up before it kills the container."""
CONTAINER_ID_WAIT_SECONDS = 10
"""How long a signal waits for `docker run` to create the container it is meant to stop."""


def check_run_id(value: str) -> str:
    """`value` if it can be a label value, else ValueError."""
    if not RUN_ID_PATTERN.fullmatch(value):
        raise ValueError("a run ID is 1 to 64 letters, digits, '.', '_' or '-', starting with a letter or digit")
    return value


def run_id_labels(run_id: str | None) -> list[str]:
    """The `docker run` arguments that label a run's container with its `--run-id`."""
    return ["--label", f"{RUN_ID_LABEL}={run_id}"] if run_id else []


class RunGuard:
    """Lets a run end in an orderly way when the CLI gets SIGTERM or SIGINT.

    While the guard is active, the first signal stops the run's container instead of ending this
    process, so that the runner still records the run's results afterwards. A second signal ends the
    process as it would have without the guard. Signal handlers can only be set in the main thread;
    elsewhere the guard does nothing.
    """

    SIGNALS = (signal.SIGTERM, signal.SIGINT)

    def __init__(self) -> None:
        self.signalled = False
        self._cidfile: Path | None = None
        self._previous: dict[signal.Signals, object] = {}

    def __enter__(self) -> "RunGuard":
        global _active
        try:
            for sig in self.SIGNALS:
                self._previous[sig] = signal.signal(sig, self._on_signal)
        except ValueError:
            self._previous.clear()
        _active = self
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        global _active
        _active = None
        self._restore()

    def _restore(self) -> None:
        for sig, handler in self._previous.items():
            _ = signal.signal(sig, handler)  # pyright: ignore[reportArgumentType]
        self._previous.clear()

    def _on_signal(self, signum: int, frame: FrameType | None) -> None:
        if self.signalled:
            self._restore()
            os.kill(os.getpid(), signum)
            return
        self.signalled = True
        logger.warning(f"Received {signal.Signals(signum).name}; stopping the container, then recording the run")
        container = self._container_id()
        if container:
            _ = subprocess.run(
                ["docker", "stop", "--time", str(STOP_GRACE_SECONDS), container], capture_output=True, text=True
            )

    def _container_id(self) -> str:
        """The ID of the container being waited on, once `docker run` has created it; empty if none."""
        if self._cidfile is None:
            return ""
        deadline = time.monotonic() + CONTAINER_ID_WAIT_SECONDS
        while True:
            try:
                container = self._cidfile.read_text().strip()
            except OSError:
                container = ""
            if container or time.monotonic() >= deadline:
                return container
            time.sleep(0.1)

    def run_container(self, command: list[str]) -> None:
        if self.signalled:
            # The signal came before there was a container to stop.
            raise subprocess.CalledProcessError(128 + signal.SIGTERM, command)
        with tempfile.TemporaryDirectory(prefix="ssebench-run-") as tmp:
            self._cidfile = Path(tmp) / "cid"
            try:
                _ = subprocess.run([*command[:2], "--cidfile", str(self._cidfile), *command[2:]], check=True)
            finally:
                self._cidfile = None


_active: RunGuard | None = None


def run_container(command: list[str]) -> None:
    """Run `command`, a foreground `docker run`, and wait for it.

    Under a `RunGuard`, a signal stops the container and this returns as the container exits.

    Raises:
        subprocess.CalledProcessError: If the container exits non-zero, also when a signal stopped it.
    """
    if _active is None:
        _ = subprocess.run(command, check=True)
    else:
        _active.run_container(command)
