"""SSEBench SDK: the task, and the build, test and grading actions of the daemon, for code in a task container.

Agents, plugins and the evaluator run inside the task container and import this package as
``sse``. It talks to ``ssebench-daemon`` over the Unix socket in ``SSE_DAEMON_SOCKET``; see
:mod:`sse.daemon`. ``import sse`` loads :mod:`sse.ai`, :mod:`sse.grading`, :mod:`sse.reference`
and :mod:`sse.tools` without contacting the daemon; :mod:`sse.project` and :mod:`sse.prompt` ask
the daemon for the task when they are imported.
"""

from importlib.metadata import version

from . import ai as ai
from . import grading as grading
from . import reference as reference
from . import tools as tools
from .error import SDKError as SDKError

__version__ = version("ssebench.sdk")
