#!/usr/bin/env python3
"""
SSEBench SDK Integration Test

This script tests the SDK functions against a real daemon and test case.
It starts the daemon, runs various SDK functions, and reports results.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from dataclasses import dataclass

# The daemon serves agents on SOCKET_PATH, gated by difficulty, and privileged
# callers on ADMIN_SOCKET_PATH. These tests drive every action and the grading
# endpoints as the evaluator does, so the SDK talks to the admin socket. Set
# before importing the SDK.
SOCKET_PATH = "/tmp/ssebench-test.sock"
ADMIN_SOCKET_PATH = "/tmp/ssebench-test-admin.sock"
os.environ["SSE_DAEMON_SOCKET"] = ADMIN_SOCKET_PATH


@dataclass
class TestResult:
    name: str
    passed: bool
    message: str


def start_daemon() -> subprocess.Popen:
    """Start the ssebench-daemon in the background."""
    print("Starting daemon...")
    proc = subprocess.Popen(
        ["ssebench-daemon"],
        env={**os.environ, "SSE_DAEMON_SOCKET": SOCKET_PATH, "SSE_ADMIN_SOCKET": ADMIN_SOCKET_PATH},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    # Wait for daemon to be ready
    time.sleep(2)

    # Check if daemon started successfully
    if proc.poll() is not None:
        stdout, stderr = proc.communicate()
        print("Daemon failed to start!")
        print(f"stdout: {stdout.decode()}")
        print(f"stderr: {stderr.decode()}")
        sys.exit(1)

    print(f"Daemon started (PID: {proc.pid})")
    return proc


def test_bash_execute() -> TestResult:
    """Test bash.execute() function."""
    from sse.tools import bash

    result = bash.execute("echo 'hello world'")

    if not result.is_success():
        return TestResult("bash.execute", False, f"Non-zero exit: {result.code}")

    if "hello world" not in result.stdout:
        return TestResult("bash.execute", False, f"Unexpected output: {result.stdout}")

    return TestResult("bash.execute", True, f"stdout={result.stdout.strip()!r}")


def test_bash_execute_failing_command() -> TestResult:
    """Test bash.execute() with a failing command."""
    from sse.tools import bash

    # Use (exit 42) in a subshell so it doesn't kill the main bash session
    result = bash.execute("(exit 42)")

    if result.code != 42:
        return TestResult("bash.execute (fail)", False, f"Expected exit 42, got {result.code}")

    return TestResult("bash.execute (fail)", True, "Correctly got exit code 42")


def test_bencher_build() -> TestResult:
    """Test bencher.build() function."""
    from sse.tools import bencher

    result = bencher.build()

    if not result.is_success():
        return TestResult(
            "bencher.build",
            False,
            f"Build failed: exit={result.code}, stderr={result.stderr[:200]}",
        )

    return TestResult("bencher.build", True, "Build succeeded")


def test_bencher_run_poc() -> TestResult:
    """Test bencher.run_poc() function - should trigger the bug (panic)."""
    from sse.tools import bencher

    result = bencher.run_poc("pocs/poc.go")

    # The PoC should FAIL because it triggers the bug
    if result.is_success():
        return TestResult(
            "bencher.run_poc",
            False,
            "PoC succeeded but should have triggered panic!",
        )

    # Check for panic in output
    output = result.stdout + result.stderr
    if "panic" not in output.lower() and "slice bounds" not in output.lower():
        return TestResult(
            "bencher.run_poc",
            False,
            f"PoC failed but no panic detected: {output[:200]}",
        )

    return TestResult(
        "bencher.run_poc",
        True,
        f"PoC correctly triggered panic (exit={result.code})",
    )


def test_bencher_function_test() -> TestResult:
    """Test bencher.function_test() - should fail due to bug."""
    from sse.tools import bencher

    result = bencher.function_test()

    # Tests should FAIL because the code is buggy
    if result.is_success():
        return TestResult(
            "bencher.function_test",
            False,
            "Tests passed but should have failed due to bug!",
        )

    return TestResult(
        "bencher.function_test",
        True,
        f"Tests correctly failed due to bug (exit={result.code})",
    )


def test_bencher_intent_test() -> TestResult:
    """Test bencher.intent_test() - should fail due to bug (patch adds more tests)."""
    from sse.tools import bencher

    result = bencher.intent_test()

    # Tests should FAIL because the code is buggy and the patch adds
    # additional tests that verify the developer's intended behaviour
    if result.is_success():
        return TestResult(
            "bencher.intent_test",
            False,
            "Tests passed but should have failed due to bug!",
        )

    return TestResult(
        "bencher.intent_test",
        True,
        f"Intent tests correctly failed due to bug (exit={result.code})",
    )


def test_capabilities() -> TestResult:
    """Test /capabilities endpoint returns correct values."""
    from sse.daemon import Daemon

    caps = Daemon().capabilities()

    expected = {
        "can_build": True,
        "can_run_poc": True,
        "poc_count": 1,
        "has_function_test": True,
        "has_intent_test": True,
    }

    if caps != expected:
        return TestResult(
            "capabilities",
            False,
            f"Expected {expected}, got {caps}",
        )

    return TestResult("capabilities", True, "All capabilities correct")


def test_final_diff_before_prepare() -> TestResult:
    """Test GET /final_diff before prepare_grading has been called."""
    from sse.daemon import Daemon

    data = Daemon().get("/final_diff")

    if "diff" not in data:
        return TestResult(
            "final_diff.before_prepare",
            False,
            f"Missing 'diff' key in response: {data}",
        )

    if data["diff"] != "":
        return TestResult(
            "final_diff.before_prepare",
            False,
            f"Expected empty diff, got: {data['diff'][:100]}",
        )

    return TestResult(
        "final_diff.before_prepare",
        True,
        "Correctly returns empty diff before prepare_grading",
    )


def test_diff() -> TestResult:
    """Test GET /diff returns agent's changes.

    Also sets up dirty state (code change + junk directory) that
    test_grading will verify gets cleaned up by prepare_grading.
    """
    from sse.daemon import Daemon
    from sse.tools import bash

    # Make a benign code change (append a comment — doesn't fix the bug)
    bash.execute("echo '// integration-test-marker: agent was here' >> /src/buggy/buggy.go")

    # Add build/ to .gitignore (simulates a real project with gitignored build dirs)
    bash.execute("echo 'build/' >> /src/buggy/.gitignore")

    # Create junk build artifacts (simulates agent running cmake/make/etc.)
    # Because build/ is gitignored, get_full_diff won't capture it.
    # The live source folder is NOT cleaned during prepare_grading — it is left
    # intact so that vendor code and cached dependencies are preserved.
    bash.execute("mkdir -p /src/buggy/build && echo 'junk' > /src/buggy/build/output.bin")

    # Commit that change, then change the tree again and add a file that is
    # never staged: the capture must take all of it, whatever was committed.
    bash.execute("cd /src/buggy && git add buggy.go && git commit -qm 'agent commit'")
    bash.execute("echo '// after-commit-marker' >> /src/buggy/buggy.go")
    bash.execute("echo 'never staged' > /src/buggy/untracked_note.txt")

    # Call GET /diff
    data = Daemon().get("/diff")

    if "diff" not in data:
        return TestResult("diff", False, f"Missing 'diff' key in response: {data}")

    diff_text = data["diff"]

    if not diff_text:
        return TestResult("diff", False, "Expected non-empty diff")

    for expected in ("integration-test-marker", "after-commit-marker", "b/untracked_note.txt"):
        if expected not in diff_text:
            return TestResult(
                "diff",
                False,
                f"Diff missing {expected!r}. Got: {diff_text[:300]}",
            )
    if "output.bin" in diff_text:
        return TestResult("diff", False, "Diff contains the gitignored build/output.bin")

    files = {f["path"]: f["status"] for f in Daemon().get("/files")["files"]}
    if files.get("untracked_note.txt") != "added" or files.get("buggy.go") != "modified":
        return TestResult("diff", False, f"Unexpected /files: {files}")

    return TestResult("diff", True, "Diff correctly contains agent's changes")


def test_grading() -> TestResult:
    """Test grading module - all tests should fail on buggy code.

    Also verifies that prepare_grading (called internally by grade()):
    - does NOT touch the live source folder (build artifacts remain)
    - applies the agent's patch to /ssebench-repo
    - saves the diff to the archive

    Grading runs build/poc/function/intent tests against /ssebench-repo.
    """
    from sse.daemon import Daemon
    from sse.tools import bash

    # Pre-condition: verify dirty state left by test_diff
    junk_check = bash.execute("test -d /src/buggy/build")
    if junk_check.code != 0:
        return TestResult(
            "grading",
            False,
            "Pre-condition failed: /src/buggy/build should exist before grading",
        )

    change_check = bash.execute("grep 'integration-test-marker' /src/buggy/buggy.go")
    if change_check.code != 0:
        return TestResult(
            "grading",
            False,
            "Pre-condition failed: code change should exist before grading",
        )

    # Run grading (which calls prepare_grading internally as step 0)
    from sse.grading import grade

    result = grade()

    # -- Verify prepare_grading behaviour --

    # Live source folder is NOT touched: junk directory must still be there
    junk_after = bash.execute("test -d /src/buggy/build")
    if junk_after.code != 0:
        return TestResult(
            "grading",
            False,
            "prepare_grading incorrectly removed /src/buggy/build (source folder must not be modified)",
        )

    # Agent's patch must have been applied to /ssebench-repo
    marker_in_repo = bash.execute("grep 'integration-test-marker' /ssebench-repo/buggy.go")
    if marker_in_repo.code != 0:
        return TestResult(
            "grading",
            False,
            "prepare_grading failed: code change was not applied to /ssebench-repo",
        )

    # GET /final_diff should have the saved diff
    final_diff_data = Daemon().get("/final_diff")
    final_diff = final_diff_data.get("diff", "")

    if not final_diff:
        return TestResult("grading", False, "GET /final_diff returned empty after prepare_grading")

    for expected in ("integration-test-marker", "after-commit-marker", "b/untracked_note.txt"):
        if expected not in final_diff:
            return TestResult(
                "grading",
                False,
                f"final_diff missing {expected!r}. Got: {final_diff[:300]}",
            )
    untracked_in_repo = bash.execute("test -f /ssebench-repo/untracked_note.txt")
    if untracked_in_repo.code != 0:
        return TestResult("grading", False, "the never-staged file was not applied to /ssebench-repo")

    # -- Verify grading results (buggy code should fail) --

    # Build should succeed even on buggy code
    if result.build_success is not True:
        return TestResult("grading", False, f"Build should succeed, got {result.build_success}")

    # Should NOT be fully successful on buggy code
    if result.is_fully_successful():
        return TestResult("grading", False, "Should not be fully successful on buggy code")

    # PoC should fail (0 out of 1 passed — the bug triggers a panic)
    if result.pov_total != 1:
        return TestResult("grading", False, f"Expected pov_total=1, got {result.pov_total}")
    if result.pov_passed != 0:
        return TestResult("grading", False, f"Expected pov_passed=0, got {result.pov_passed}")

    # All test types should fail on buggy code
    if result.func_test_success is not False:
        return TestResult("grading", False, "func_test_success should be False")
    if result.intent_test_success is not False:
        return TestResult("grading", False, "intent_test_success should be False")

    # First failure should have been recorded
    if result.error_msg is None:
        return TestResult("grading", False, "error_msg should be set")
    if result.error_log is None:
        return TestResult("grading", False, "error_log should be set")

    return TestResult(
        "grading",
        True,
        "Grading correctly cleans up and reports all failures on buggy code",
    )


def test_daemon_error_handling() -> TestResult:
    """Test that daemon errors raise SDKError."""
    from sse.daemon import Daemon
    from sse.error import SDKError

    daemon = Daemon()

    try:
        # Call bencher with an invalid action - this should raise SDKError
        daemon.tool("bencher", "invalid_action_xyz", {})
        return TestResult(
            "daemon.error_handling",
            False,
            "Expected SDKError but no exception was raised",
        )
    except SDKError as e:
        # Check that the error message contains the expected text
        if "invalid action" in e.message:
            return TestResult(
                "daemon.error_handling",
                True,
                f"Correctly raised SDKError: {e.message}",
            )
        return TestResult(
            "daemon.error_handling",
            False,
            f"SDKError raised but unexpected message: {e.message}",
        )
    except Exception as e:
        return TestResult(
            "daemon.error_handling",
            False,
            f"Expected SDKError but got {type(e).__name__}: {e}",
        )


def run_all_tests() -> list[TestResult]:
    """Run all integration tests."""
    tests = [
        ("bash.execute", test_bash_execute),
        ("bash.execute (fail)", test_bash_execute_failing_command),
        ("bencher.build", test_bencher_build),
        ("bencher.run_poc", test_bencher_run_poc),
        ("bencher.function_test", test_bencher_function_test),
        ("bencher.intent_test", test_bencher_intent_test),
        ("capabilities", test_capabilities),
        ("final_diff.before_prepare", test_final_diff_before_prepare),
        ("diff", test_diff),
        ("grading", test_grading),
        ("daemon.error_handling", test_daemon_error_handling),
    ]

    results = []
    for name, test_fn in tests:
        print(f"\n{'=' * 60}")
        print(f"Running: {name}")
        print("=" * 60)
        try:
            result = test_fn()
            results.append(result)
            status = "PASS" if result.passed else "FAIL"
            print(f"  [{status}] {result.message}")
        except Exception as e:
            results.append(TestResult(name, False, f"Exception: {e}"))
            print(f"  [FAIL] Exception: {e}")
            import traceback

            traceback.print_exc()

    return results


def print_summary(results: list[TestResult]) -> bool:
    """Print test summary and return True if all passed."""
    print("\n")
    print("=" * 60)
    print("INTEGRATION TEST SUMMARY")
    print("=" * 60)

    passed = sum(1 for r in results if r.passed)
    total = len(results)

    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(f"  [{status}] {r.name}: {r.message}")

    print("-" * 60)
    print(f"Results: {passed}/{total} tests passed")

    if passed == total:
        print("\nAll tests passed!")
        return True
    else:
        print(f"\n{total - passed} test(s) failed!")
        return False


def main():
    """Main entry point."""
    print("SSEBench SDK Integration Test")
    print("=" * 60)

    # Start daemon
    daemon = start_daemon()

    try:
        # Run tests
        results = run_all_tests()

        # Print summary
        success = print_summary(results)

        # Exit with appropriate code
        sys.exit(0 if success else 1)

    finally:
        # Clean up daemon
        print("\nStopping daemon...")
        daemon.terminate()
        daemon.wait(timeout=5)
        print("Daemon stopped.")


if __name__ == "__main__":
    main()
