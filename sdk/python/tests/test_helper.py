"""Unit tests for sse.helper module."""

from __future__ import annotations

import pytest

from sse.error import SDKError
from sse.helper import ScriptResult, wrap_result


class TestSDKError:
    """Tests for SDKError exception."""

    def test_wraps_message(self):
        err = SDKError("something failed")
        assert err.message == "something failed"
        assert "something failed" in str(err)

    def test_str_representation(self):
        err = SDKError("something failed")
        assert str(err) == "something failed"


class TestScriptResult:
    """Tests for ScriptResult dataclass."""

    def test_is_success_with_zero_exit_code(self):
        result = ScriptResult(code=0, stdout="output", stderr="")
        assert result.is_success() is True

    def test_is_success_with_nonzero_exit_code(self):
        result = ScriptResult(code=1, stdout="", stderr="error")
        assert result.is_success() is False

    def test_str_contains_exit_code_info(self):
        result = ScriptResult(code=0, stdout="", stderr="")
        assert "exit code" in str(result).lower()


class TestWrapResult:
    """Tests for wrap_result decorator."""

    def test_wraps_valid_data_to_dataclass(self):
        @wrap_result(ScriptResult)
        def get_result():
            return {"code": 0, "stdout": "hello", "stderr": ""}

        result = get_result()
        assert isinstance(result, ScriptResult)
        assert result.code == 0
        assert result.stdout == "hello"

    def test_raises_sdk_error_for_none(self):
        @wrap_result(ScriptResult)
        def get_none():
            return None

        with pytest.raises(SDKError) as exc_info:
            get_none()

        assert "None" in exc_info.value.message

    def test_raises_sdk_error_for_invalid_data(self):
        @wrap_result(ScriptResult)
        def get_invalid():
            # Missing required fields for ScriptResult (no 'error' key)
            return {"foo": "bar"}

        with pytest.raises(SDKError) as exc_info:
            get_invalid()

        assert "unexpected response format" in exc_info.value.message

    def test_preserves_function_arguments(self):
        @wrap_result(ScriptResult)
        def echo(value: str):
            return {"code": 0, "stdout": value, "stderr": ""}

        result = echo("test input")
        assert isinstance(result, ScriptResult)
        assert result.stdout == "test input"
