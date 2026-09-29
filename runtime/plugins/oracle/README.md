# Oracle Plugin

This plugin tries to generate deterministic oracle for SSEBench task to improve
the test coverage for the tested project.

An oracle is a "judge" that runs a check on the result and returns if the bug is
well-patched or not.

A *deterministic* oracle is one doesn't rely on LLM reasoning. Thus make it
perfect to fit in the SSEBench grading pipeline.

The plugin does *NOT* affect the actual grading. The purpose is to generate new
oracles for human to review.
