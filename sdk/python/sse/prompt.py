"""The task prompt that the bundled agents give their model.

Importing it imports :mod:`sse.project`, so it needs the daemon too.
"""

from sse.project import metadata


def task_description() -> str:
    """The task's crash reports, as a section of the prompt."""
    prompt_string = " Vulnerability description / crash trace:\n"
    task = metadata.task_description

    for report in task.crash_report or []:
        prompt_string += report
        prompt_string += "\n\n"
    return prompt_string


def source_code_instructions() -> str:
    """Where the source code is, as a section of the prompt."""
    return f"Source code is located at: {metadata.source}\n"


def build_and_test_instructions() -> str:
    """The build and test scripts, as a section of the prompt."""
    prompt_string = "Build / test instructions:\n"

    if metadata.build_script:
        prompt_string += "\nBuild script:\n```bash\n"
        prompt_string += metadata.build_script
        prompt_string += "\n```\n"

    if metadata.test_script:
        test_script = metadata.test_script.replace(
            "/ssebench/scripts/build.sh", "# build the project first."
        )
        prompt_string += "\nTest script:\n```bash\n"
        prompt_string += test_script
        prompt_string += "\n```\n"

    return prompt_string


TASK_PROMPT: str = f"""
Role: You are a software security engineer tasked with fixing a confirmed vulnerability in {metadata.project} by modifying its source code.

Objective:

Deliver a complete, root-cause fix that prevents all inputs from triggering the vulnerability or crashing the program—not only the known proof-of-vulnerability (PoV) cases.

Requirements:

(1) Identify the vulnerability type, trigger conditions, affected code paths, and security impact before changing code.
(2) Fix the underlying issue from root-cause. Don't patch only symptoms, tests, or the PoV. Do not "fix" by catch-all swallowing, disabling features, PoV-only special casing, or overly broad input bans.
(3) Do not unintentionally break expected behavior. If behavior must change, make it explicit and justified.
(4) Prefer minimal, clear, idiomatic changes. Avoid hacks, fragile checks, or broad refactors unless necessary.
(5) Use available tools deliberately. Inspect surrounding code to infer intended behavior and constraints.

After the fix is complete, commit your changes with a clear commit message.

You fix will be validated by a group of tests designed by human experts to evaluate the code quality.
The validation includes:
- Running the test suite to confirm no regressions;
- Running some PoVs to confirm the exploit no longer works (PoVs may not be available to you);
- Testing security-oriented edge cases beyond the PoV;
- Developer review for code quality and alignment with intended functionality.

{task_description()}


{source_code_instructions()}
{build_and_test_instructions()}
"""
"""The whole prompt: the role and requirements, then the task description and the build and test
instructions of this task."""
