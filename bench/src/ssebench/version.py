"""The SSEBench version.

Every component shares the version in the repository's VERSION file, which is
SemVer. Python metadata holds its PEP 440 form (1.0.0rc1 for 1.0.0-rc.1), so
`__version__` is that form and `VERSION` converts it back for image tags and
for comparison with the other components.
"""

import re
from importlib.metadata import version

__version__ = version("ssebench")

_PEP440 = re.compile(r"(?P<release>\d+\.\d+\.\d+)(?:(?P<pre>a|b|rc)(?P<num>\d+)|(?P<dev>\.dev0))?")
_SEMVER_PRE = {"a": "alpha", "b": "beta", "rc": "rc"}


def semver(pep440: str) -> str:
    """Return the VERSION form of a PEP 440 version that tools/release/bump.py wrote."""
    m = _PEP440.fullmatch(pep440)
    if m is None:
        return pep440
    if m["pre"]:
        return f"{m['release']}-{_SEMVER_PRE[m['pre']]}.{m['num']}"
    if m["dev"]:
        return f"{m['release']}-dev"
    return m["release"]


VERSION = semver(__version__)
