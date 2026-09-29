import logging
import os
import subprocess
from pathlib import Path

from sse import project

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def backup_src():
    source = project.metadata.source
    archive = os.getenv("SSE_ARCHIVE")
    if not archive:
        return

    logger.info("[evaluator] backup source...")
    try:
        _ = subprocess.run(
            ["tar", "czf", f"{Path(archive) / 'source.tar.gz'}", "-C", source, "."],
            check=False,
            capture_output=True,
        )
    except Exception:
        pass
