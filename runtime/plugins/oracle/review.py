# Patch review using the OpenCode agent.
#
# Based on early experiments, this agent produces reviews that are strongly biased
# toward the "ground-truth patch". However, this is acceptable. The goal of this
# "deterministic oracle generation" is to reduce the reviewer’s false positive rate.
#
# NOTE: In the prompt, I replaced the phrase "ground truth" with "another candidate fix"
# to encourage the model to perform a more balanced comparison.
#
# The judgment report will be used in the next stage to guide harness generation in the
# fuzzing pipeline.

import logging
from pathlib import Path

from sse import project as sse_project
from sse.reference import get_reference_patch

from config import make_opencode_agent

REVIEW_PROMPT_TEMPLATE = """\
An AI agent has attempted to fix a bug in this directory ({source_dir}). \
Another candidate fix written by human is provided below.

<candidate-fix>
{ground_truth_patch}
</candidate-fix>

Please analyze both approaches:
1. Compare the agent's changes (use git diff) against the candidate above
2. Identify any differences in methodology or implementation
3. Highlight what the agent did well and what could be improved
4. Assess whether the agent's fix addresses the root cause
5. Provide insights on the quality and correctness of the agent's fix

Notice both agent and human can make mistake.

Be specific and cite code examples where relevant."""

logger = logging.getLogger(__name__)


async def run_review(archive_path: str) -> str | None:
    """Run an AI review of the agent's patch vs ground truth.

    Starts an OpenCode agent, sends a review prompt comparing the agent's
    changes (via ``git diff``) against the ground truth patch. Writes the
    full response to ``{archive_path}/review.txt``.

    Args:
        archive_path: Directory to write the review log to.

    Returns:
        The review text on success, ``None`` on failure or skip.
    """
    try:
        # Retrieve the reference patch from the daemon (post-agent plugin).
        reference_patch = get_reference_patch()
        if not reference_patch:
            logger.warning("No reference patch available, skipping review")
            return None

        source_dir = str(sse_project.metadata.source)
        prompt = REVIEW_PROMPT_TEMPLATE.format(
            source_dir=source_dir,
            ground_truth_patch=reference_patch,
        )

        logger.info("Starting AI patch review...")
        async with make_opencode_agent() as agent:
            session_id = await agent.create_session(title="Patch Review")
            response = await agent.send_prompt(session_id, prompt)

        if not response.final_message.strip():
            logger.warning("The model returned no review; check the model and its key")

        # Write review artifacts to archive
        archive = Path(archive_path)
        archive.mkdir(parents=True, exist_ok=True)

        # Full agent dialog (all messages, for debugging/analysis)
        dialog_out = archive / "ai_review_dialog.txt"
        _ = dialog_out.write_text(response.full_log)
        logger.info(f"Full review dialog written to {dialog_out}")

        # Final message only (concise review output)
        review_out = archive / "review.txt"
        _ = review_out.write_text(response.final_message)
        logger.info(f"Review written to {review_out}")

        return response.final_message

    except Exception as e:
        logger.error(f"AI review failed (non-fatal): {e}")
        return None
