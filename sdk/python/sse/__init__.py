from importlib.metadata import version

from . import ai as ai
from . import cheating as cheating
from . import grading as grading
from . import tools as tools
from .error import SDKError as SDKError

__version__ = version("ssebench.sdk")
