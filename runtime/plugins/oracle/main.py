# Oracle plugin: generate material for a human to build a deterministic oracle
# for a task, using the run's model. It never affects the grade.
#
# It runs at after-grading, so the agent has finished and the reference patch is
# available to post-agent tooling. It writes its outputs under `oracle/` in the
# results directory.
#
# Assumptions:
#  - It runs inside an SSEBench container, as root, at the grading phase.
#  - The run's model is reachable through LiteLLM, configured by SSE_MODEL_NAME,
#    SSE_BASE_URL and SSE_API_KEY (the plugin declares `llm: true`).
#  - The agent's patch is read from the daemon's admin socket (`/final_diff`), not
#    with git: the repository belongs to the agent's user, and git refuses to run
#    in it as root.
#
# Fuzzing (review then fuzz) is opt-in with SSE_ORACLE_FUZZ=1: it installs and
# runs AFL++, so it needs `--egress open`. By default the plugin only produces
# the LLM patch review, which needs no internet.

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="[oracle] %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

LLM_VARS = ("SSE_API_KEY", "SSE_BASE_URL", "SSE_MODEL_NAME")


def output_dir() -> Path:
    archive = Path(os.environ.get("SSE_ARCHIVE", "/tmp/sse-archive"))
    return archive / "oracle"


def report_skipped(reason: str) -> None:
    logger.warning("%s; skipping", reason)
    # The entrypoint records the plugin as skipped and logs the reason on the
    # run's console; the file is only set when the entrypoint runs the plugin.
    skip_file = os.environ.get("SSE_PLUGIN_SKIP_FILE")
    if skip_file:
        Path(skip_file).write_text(reason + "\n")


def llm_ready() -> bool:
    missing = [v for v in LLM_VARS if not os.environ.get(v)]
    if missing:
        report_skipped(f"No LLM configured ({', '.join(missing)} unset)")
        return False
    return True


async def run(out: Path) -> None:
    # Import lazily: these modules reach the daemon and the model, which only
    # exist inside a running container.
    from fuzz import run_fuzz
    from review import run_review

    review_text = None
    try:
        review_text = await run_review(str(out))
    except Exception as e:
        logger.error("Patch review failed (non-fatal): %s", e)

    if os.environ.get("SSE_ORACLE_FUZZ") == "1":
        try:
            await run_fuzz(review_text)
        except Exception as e:
            logger.error("Fuzzing failed (non-fatal): %s", e)
    else:
        logger.info("Fuzzing disabled (set SSE_ORACLE_FUZZ=1 with --egress open to enable)")


def main() -> int:
    if not llm_ready():
        return 0
    out = output_dir()
    out.mkdir(parents=True, exist_ok=True)
    asyncio.run(run(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
