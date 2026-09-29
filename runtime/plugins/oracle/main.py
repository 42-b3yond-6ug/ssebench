# Disclaimer: this is a purely experimental plugin for generating deterministic
# oracles for SSEBench tasks.
#
# Plugin APIs and SDK AI APIs are not stable.
# This plugin may be refactored in the near future.
#
# The plugin makes several assumptions, including some important ones:
# 1. We are running inside an SSEBench container. The plugin is LLM-assisted and
#    uses the run's model through LiteLLM, configured by `SSE_MODEL_NAME`,
#    `SSE_BASE_URL` and `SSE_API_KEY`.
# 2. An agent has successfully committed a patch to the original repo, meaning the
#    repo now contains two and only two commits: a buggy commit and a fix commit.
# 3. The project is not broken in a way that prevents fuzzing from running.
# 4. Internet access is allowed. It will use the internet to install `afl++`.
#    TODO: AFL++ will be included in the base image / tool layer so we don't
#    need to install it again.

import asyncio

from fuzz import run_fuzz
from review import run_review

archive_folder = "/tmp/"


async def main():
    review_text = await run_review(archive_folder)
    await run_fuzz(review_text)


if __name__ == "__main__":
    asyncio.run(main())
