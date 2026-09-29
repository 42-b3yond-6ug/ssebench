import logging
import subprocess

from sse import project
from sse.ai import OpenCodeAgent, build_opencode_config

logger = logging.getLogger(__name__)


FUZZING_PROMPT_TEMPLATE = """
This repo contains a bug, and a patch may has been applied to this repo.
Your job is to setup a fuzzing to test if the bug still exists or not.

Some backgrounds:
- /ssebench/scripts contains some script we used for building and testing.
- we run build.sh and run.sh to test the PoC.
  You are welcome to test if the PoC is migrated before fuzzing.
- /ssebench/reports contains some descriptions about the bug.
- A fix at /ssebench/diffs/patch.diff is another attempt of fix of the bug,
  but is not the one we applied to the repo.

<code_review>
{review}
</code_review>

Steps:

0. see if AFL++ is available, if not, install it.
1. /harness-generation either pick or generate a fuzzing harness.
2. /seeds-collection prepare some seeds.
3. /fuzzing run the fuzzer for 5 minutes only. You must stop after 5 minutes.

You should look at skills in /plugins/oracle/skills to understand your job.

In the end, report the fuzzing result.
"""


# Load skills to opencode configs
def load_skills(src_dir: str):
    _ = subprocess.run(["mkdir", "-p", f"{src_dir}/.opencode"])
    _ = subprocess.run(["cp", "-r", "/evaluator/skills", f"{src_dir}/.opencode/"])


async def run_fuzz(review: str | None):
    config = build_opencode_config()
    src_dir = str(project.source.absolute())

    load_skills(src_dir)

    async with OpenCodeAgent(directory=src_dir, config=config) as agent:
        session_id = await agent.create_session()
        prompt = FUZZING_PROMPT_TEMPLATE.format(review=review)
        response = await agent.send_prompt(session_id, prompt, timeout=36000)
        logger.info(response)
