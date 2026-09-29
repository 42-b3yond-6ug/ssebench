"""Unit tests for sse.grading module (PatchResult only, no daemon needed)."""

from __future__ import annotations

from sse.grading import PatchResult


class TestPatchResultSuccess:
    """Tests for is_fully_successful()."""

    def test_all_none_is_successful(self):
        """Nothing ran -> vacuously successful."""
        result = PatchResult()
        assert result.is_fully_successful() is True

    def test_all_passing(self):
        result = PatchResult(
            build_success=True,
            pov_passed=3,
            pov_total=3,
            func_test_success=True,
            intent_test_success=True,
        )
        assert result.is_fully_successful() is True

    def test_partial_none_all_passing(self):
        """Some steps not applicable (None), the rest pass."""
        result = PatchResult(
            build_success=True,
            func_test_success=True,
        )
        assert result.is_fully_successful() is True

    def test_build_failure(self):
        result = PatchResult(build_success=False)
        assert result.is_fully_successful() is False

    def test_poc_partial_failure(self):
        result = PatchResult(
            build_success=True,
            pov_passed=1,
            pov_total=3,
        )
        assert result.is_fully_successful() is False

    def test_poc_zero_passed(self):
        result = PatchResult(
            build_success=True,
            pov_passed=0,
            pov_total=2,
        )
        assert result.is_fully_successful() is False

    def test_poc_all_passed(self):
        result = PatchResult(
            build_success=True,
            pov_passed=2,
            pov_total=2,
        )
        assert result.is_fully_successful() is True

    def test_func_test_failure(self):
        result = PatchResult(
            build_success=True,
            func_test_success=False,
        )
        assert result.is_fully_successful() is False

    def test_intent_test_failure(self):
        result = PatchResult(
            build_success=True,
            func_test_success=True,
            intent_test_success=False,
        )
        assert result.is_fully_successful() is False


class TestPatchResultMarkFailure:
    """Tests for mark_failure()."""

    def test_sets_error_fields(self):
        result = PatchResult()
        result.mark_failure("something broke", "full log here")
        assert result.error_msg == "something broke"
        assert result.error_log == "full log here"

    def test_first_failure_wins(self):
        result = PatchResult()
        result.mark_failure("first error", "first log")
        result.mark_failure("second error", "second log")
        assert result.error_msg == "first error"
        assert result.error_log == "first log"

    def test_log_is_optional(self):
        result = PatchResult()
        result.mark_failure("error without log")
        assert result.error_msg == "error without log"
        assert result.error_log is None

    def test_noop_when_already_set(self):
        result = PatchResult()
        result.mark_failure("original", "original log")
        result.mark_failure("overwrite attempt", "new log")
        assert result.error_msg == "original"
        assert result.error_log == "original log"
