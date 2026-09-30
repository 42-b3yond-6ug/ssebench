"""How a run is identified from outside and how it ends when the CLI is asked to stop.

A tool that starts `ssebench run` labels the run with its own ID and finds its containers by it, rather
than by task, which several runs can share. The CLI also waits for the run in the foreground, so a
SIGTERM to the CLI would otherwise end it with no summary, and no record of what the run spent.
"""

import logging
import os
import re
import signal
from pathlib import Path
from types import FrameType, TracebackType

from ssebench.backends import RUN_ID_LABEL, STOP_GRACE_SECONDS, Backend, RunHandle, RunSpec
from ssebench.runner.layout import LATEST

__all__ = ["RUN_ID_LABEL", "RUN_ID_PATTERN", "RunGuard", "check_run_id", "execute"]

logger = logging.getLogger(__name__)

RUN_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")


def check_run_id(value: str) -> str:
    """`value` if it can be a label value and a directory name, else ValueError."""
    if not RUN_ID_PATTERN.fullmatch(value):
        raise ValueError("a run ID is 1 to 64 letters, digits, '.', '_' or '-', starting with a letter or digit")
    # `latest` is the link beside the run directories; the check is case-blind for case-folding file systems.
    if value.lower() == LATEST:
        raise ValueError(f"'{LATEST}' is not a run ID: it names the newest run of a task, model and agent")
    return value


class RunGuard:
    """Lets a run end in an orderly way when the CLI gets SIGTERM or SIGINT.

    While the guard is active, the first signal stops the run's containers instead of ending this
    process, so that the runner still records the run's results afterwards. A second signal ends the
    process as it would have without the guard. Signal handlers can only be set in the main thread;
    elsewhere the guard does nothing.
    """

    SIGNALS = (signal.SIGTERM, signal.SIGINT)

    def __init__(self) -> None:
        self.signalled = False
        self._run: tuple[Backend, RunHandle] | None = None
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
        if self._run is not None:
            backend, handle = self._run
            backend.stop(handle, STOP_GRACE_SECONDS)

    def attach(self, backend: Backend, handle: RunHandle) -> None:
        """Make `handle` the run that a signal stops; stop it now if the signal has already come."""
        self._run = (backend, handle)
        if self.signalled:
            backend.stop(handle, STOP_GRACE_SECONDS)

    def detach(self) -> None:
        self._run = None


_active: RunGuard | None = None


def execute(backend: Backend, spec: RunSpec, results: Path) -> int:
    """Start the run, wait for it, collect its results into `results` and clean up; return the exit status.

    Under a `RunGuard`, a signal stops the run and this returns once it exits. A signal that comes before
    there is a run to stop starts nothing and returns 128 plus SIGTERM.

    Raises:
        BackendError: If the run cannot be started or its results cannot be collected.
    """
    guard = _active
    if guard is not None and guard.signalled:
        return 128 + signal.SIGTERM
    handle = backend.start(spec)
    try:
        if guard is not None:
            guard.attach(backend, handle)
        status = backend.wait(handle)
        backend.collect_results(handle, results)
        return status
    finally:
        if guard is not None:
            guard.detach()
        backend.cleanup(handle)
