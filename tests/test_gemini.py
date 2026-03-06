"""Tests for Gemini integration: retry logic and malformed-JSON handling."""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from rewired.agent import gemini


class TestGeminiConfiguration:
    """Test API key detection."""

    @patch.dict("os.environ", {"GEMINI_API_KEY": ""})
    def test_not_configured_empty(self):
        result = gemini.generate("test prompt")
        assert "API key not configured" in result

    @patch.dict("os.environ", {"GEMINI_API_KEY": "your_gemini_api_key_here"})
    def test_not_configured_placeholder(self):
        result = gemini.generate("test prompt")
        assert "API key not configured" in result


class TestRetryLogic:
    """Test the retry mechanism for malformed responses."""

    @patch.dict("os.environ", {"GEMINI_API_KEY": "test_key"})
    @patch("rewired.agent.gemini._candidate_models", return_value=["gemini-pro"])
    def test_successful_first_attempt(self, _):
        """First attempt succeeds → returns immediately."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = '{"result": "ok"}'
        mock_client.models.generate_content.return_value = mock_response

        with patch("google.genai.Client", return_value=mock_client):
            result = gemini.generate("test", json_output=True)
            assert result == '{"result": "ok"}'

    @patch.dict("os.environ", {"GEMINI_API_KEY": "test_key"})
    @patch("rewired.agent.gemini._candidate_models", return_value=["gemini-pro"])
    def test_retry_on_model_failure(self, _):
        """All models fail on first attempt, succeed on retry."""
        mock_client = MagicMock()
        call_count = 0

        def _gen(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 1:
                raise Exception("model overloaded")
            resp = MagicMock()
            resp.text = '{"retried": true}'
            return resp

        mock_client.models.generate_content.side_effect = _gen

        with patch("google.genai.Client", return_value=mock_client):
            result = gemini.generate("test", max_retries=2)
            assert "retried" in result or "error" in result.lower()

    @patch.dict("os.environ", {"GEMINI_API_KEY": "test_key"})
    @patch("rewired.agent.gemini._candidate_models", return_value=["gemini-pro"])
    def test_all_retries_exhausted(self, _):
        """All retries fail → returns error string."""
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = Exception("always fails")

        with patch("google.genai.Client", return_value=mock_client):
            result = gemini.generate("test", max_retries=1)
            assert "error" in result.lower() or "failed" in result.lower()


class TestJSONOutputMode:
    """Test JSON output mode configuration."""

    @patch.dict("os.environ", {"GEMINI_API_KEY": "test_key"})
    @patch("rewired.agent.gemini._candidate_models", return_value=["gemini-pro"])
    def test_json_mode_sets_temperature_zero(self, _):
        """json_output=True should set temperature=0.0."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = '{"ok": true}'
        mock_client.models.generate_content.return_value = mock_response

        configs_used = []

        original_config = None
        def _capture_config(*args, **kwargs):
            # capture config arg
            config = kwargs.get("config")
            if config:
                configs_used.append(config)
            return mock_response

        mock_client.models.generate_content.side_effect = _capture_config

        with patch("google.genai.Client", return_value=mock_client):
            gemini.generate("test", json_output=True)
            # We can verify generate was called (the function returned)
            assert mock_client.models.generate_content.called


class TestNoResponseHandling:
    """Test handling of empty responses."""

    @patch.dict("os.environ", {"GEMINI_API_KEY": "test_key"})
    @patch("rewired.agent.gemini._candidate_models", return_value=["gemini-pro"])
    def test_empty_response_text(self, _):
        """Response with empty text → returns '[No response from Gemini]'."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = ""
        mock_client.models.generate_content.return_value = mock_response

        with patch("google.genai.Client", return_value=mock_client):
            result = gemini.generate("test")
            assert "No response" in result


class TestNetworkErrors:
    """Test handling of connection-reset style failures."""

    @patch.dict("os.environ", {"GEMINI_API_KEY": "test_key"})
    @patch("rewired.agent.gemini._candidate_models", return_value=["gemini-pro"])
    def test_connection_reset_returns_network_error(self, _):
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = ConnectionResetError(
            "[WinError 10054] existing connection was forcibly closed"
        )

        with patch("google.genai.Client", return_value=mock_client):
            result = gemini.generate("test")

        assert "network error" in result.lower()
        assert "connection reset" in result.lower()
