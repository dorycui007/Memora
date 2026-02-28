"""Tests for the retry utility module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import openai
import pytest

from memora.core.retry import (
    call_with_retry,
    compute_delay,
    is_retryable,
    retry_on_transient,
)


# ── is_retryable ──────────────────────────────────────────────────────────────


class TestIsRetryable:
    def test_rate_limit_error_is_retryable(self):
        exc = openai.RateLimitError(
            message="rate limited",
            response=MagicMock(status_code=429),
            body=None,
        )
        assert is_retryable(exc) is True

    def test_internal_server_error_is_retryable(self):
        exc = openai.InternalServerError(
            message="internal error",
            response=MagicMock(status_code=500),
            body=None,
        )
        assert is_retryable(exc) is True

    def test_api_connection_error_is_retryable(self):
        exc = openai.APIConnectionError(request=MagicMock())
        assert is_retryable(exc) is True

    def test_auth_error_is_not_retryable(self):
        exc = openai.AuthenticationError(
            message="bad key",
            response=MagicMock(status_code=401),
            body=None,
        )
        assert is_retryable(exc) is False

    def test_bad_request_is_not_retryable(self):
        exc = openai.BadRequestError(
            message="bad request",
            response=MagicMock(status_code=400),
            body=None,
        )
        assert is_retryable(exc) is False

    def test_httpx_connect_timeout_is_retryable(self):
        exc = httpx.ConnectTimeout("timeout")
        assert is_retryable(exc) is True

    def test_httpx_read_timeout_is_retryable(self):
        exc = httpx.ReadTimeout("timeout")
        assert is_retryable(exc) is True

    def test_httpx_500_status_is_retryable(self):
        response = MagicMock()
        response.status_code = 502
        exc = httpx.HTTPStatusError("bad gateway", request=MagicMock(), response=response)
        assert is_retryable(exc) is True

    def test_httpx_400_status_is_not_retryable(self):
        response = MagicMock()
        response.status_code = 400
        exc = httpx.HTTPStatusError("bad request", request=MagicMock(), response=response)
        assert is_retryable(exc) is False

    def test_generic_exception_is_not_retryable(self):
        assert is_retryable(ValueError("oops")) is False


# ── compute_delay ─────────────────────────────────────────────────────────────


class TestComputeDelay:
    def test_first_attempt_bounded_by_base(self):
        for _ in range(50):
            d = compute_delay(0, base_delay=1.0, max_delay=30.0)
            assert 0 <= d <= 1.0

    def test_delay_increases_with_attempts(self):
        # Statistical: average delay should increase with attempts
        avg_0 = sum(compute_delay(0) for _ in range(100)) / 100
        avg_3 = sum(compute_delay(3) for _ in range(100)) / 100
        assert avg_3 > avg_0

    def test_delay_capped_by_max(self):
        for _ in range(50):
            d = compute_delay(100, base_delay=1.0, max_delay=5.0)
            assert d <= 5.0


# ── retry_on_transient decorator ──────────────────────────────────────────────


class TestRetryOnTransient:
    @patch("memora.core.retry.time.sleep")
    def test_succeeds_on_first_try(self, mock_sleep):
        @retry_on_transient(max_retries=3)
        def fn():
            return "ok"

        assert fn() == "ok"
        mock_sleep.assert_not_called()

    @patch("memora.core.retry.time.sleep")
    def test_retries_on_transient_then_succeeds(self, mock_sleep):
        call_count = 0

        @retry_on_transient(max_retries=3)
        def fn():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise openai.RateLimitError(
                    message="rate limited",
                    response=MagicMock(status_code=429),
                    body=None,
                )
            return "ok"

        assert fn() == "ok"
        assert call_count == 3
        assert mock_sleep.call_count == 2

    @patch("memora.core.retry.time.sleep")
    def test_raises_after_max_retries(self, mock_sleep):
        @retry_on_transient(max_retries=2)
        def fn():
            raise openai.RateLimitError(
                message="rate limited",
                response=MagicMock(status_code=429),
                body=None,
            )

        with pytest.raises(openai.RateLimitError):
            fn()
        assert mock_sleep.call_count == 2

    @patch("memora.core.retry.time.sleep")
    def test_does_not_retry_non_retryable(self, mock_sleep):
        @retry_on_transient(max_retries=3)
        def fn():
            raise openai.AuthenticationError(
                message="bad key",
                response=MagicMock(status_code=401),
                body=None,
            )

        with pytest.raises(openai.AuthenticationError):
            fn()
        mock_sleep.assert_not_called()


# ── call_with_retry ───────────────────────────────────────────────────────────


class TestCallWithRetry:
    @patch("memora.core.retry.time.sleep")
    def test_succeeds_immediately(self, mock_sleep):
        result = call_with_retry(lambda: "ok")
        assert result == "ok"
        mock_sleep.assert_not_called()

    @patch("memora.core.retry.time.sleep")
    def test_retries_then_succeeds(self, mock_sleep):
        call_count = 0

        def fn():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx.ConnectTimeout("timeout")
            return "ok"

        result = call_with_retry(fn, max_retries=2)
        assert result == "ok"
        assert call_count == 2

    @patch("memora.core.retry.time.sleep")
    def test_passes_args_and_kwargs(self, mock_sleep):
        def fn(a, b, c=10):
            return a + b + c

        result = call_with_retry(fn, 1, 2, c=3)
        assert result == 6
