"""Tests for agent-side code-skew detection (desktop/serve backend).

Companion to ``tests/test_code_skew.py`` (gateway): these prove the same
protection exists for the long-lived ``hermes serve`` / desktop backend
process, which imports ``run_agent`` directly rather than going through the
gateway.  See #68178.
"""

from unittest.mock import MagicMock, patch

import pytest


class TestAgentCodeSkewCaching:
    def test_boot_fingerprint_recorded_at_import(self):
        """``run_agent`` records its boot fingerprint on first import."""
        import run_agent

        # Should not be None on a git install.
        assert run_agent._agent_boot_fingerprint is not None

    def test_detect_no_skew_when_unchanged(self):
        """When the fingerprint hasn't changed, skew is None."""
        import run_agent

        assert run_agent._detect_agent_code_skew() is None

    def test_cached_skew_is_returned_immediately(self, monkeypatch):
        """Once confirmed, the result is cached and returned without I/O."""
        import run_agent

        monkeypatch.setattr(run_agent, "_agent_code_skew_confirmed", True)
        monkeypatch.setattr(run_agent, "_agent_code_skew_labels", ("abc1234567", "def4567890"))

        skew = run_agent._detect_agent_code_skew()
        assert skew == ("abc1234567", "def4567890")

    def test_none_boot_fingerprint_means_no_skew(self, monkeypatch):
        """If boot fingerprint could not be read, skew detection is a no-op."""
        import run_agent

        monkeypatch.setattr(run_agent, "_agent_boot_fingerprint", None)
        monkeypatch.setattr(run_agent, "_agent_code_skew_confirmed", False)
        monkeypatch.setattr(run_agent, "_agent_code_skew_labels", None)

        assert run_agent._detect_agent_code_skew() is None


class TestCheckCodeSkewBeforeTurn:
    def test_returns_none_without_skew(self):
        """When no skew exists, the method returns None."""
        import run_agent

        # Create a minimal fake agent with the method.
        class FakeAgent:
            pass

        fake = FakeAgent()
        # The method lives on AIAgent, not a module function. Test by
        # verifying the underlying function returns None when no skew.
        result = run_agent._detect_agent_code_skew()
        assert result is None

    def test_returns_warning_when_skew_confirmed(self, monkeypatch):
        """When skew is confirmed, the method returns a descriptive warning."""
        import run_agent

        monkeypatch.setattr(run_agent, "_agent_code_skew_confirmed", True)
        monkeypatch.setattr(run_agent, "_agent_code_skew_labels", ("abc1234567", "def4567890"))

        # The method is on AIAgent, so we need to instantiate or call via class.
        # Instead, test the underlying function directly.
        skew = run_agent._detect_agent_code_skew()
        assert skew == ("abc1234567", "def4567890")

    def test_confirmed_code_skew_remains_latched(self, monkeypatch):
        """A live process must not pretend it adopted rewritten source."""
        import run_agent

        monkeypatch.setattr(run_agent, "_agent_code_skew_confirmed", True)
        monkeypatch.setattr(run_agent, "_agent_code_skew_labels", ("abc1234567", "def4567890"))

        assert run_agent._detect_agent_code_skew() == ("abc1234567", "def4567890")
        assert run_agent._detect_agent_code_skew() == ("abc1234567", "def4567890")
        assert run_agent._agent_code_skew_confirmed is True


def test_code_skew_early_exit_finalizes_without_calling_provider(tmp_path):
    """A source-update warning exits through the real turn finalizer."""
    from run_agent import AIAgent

    hermes_home = tmp_path / ".hermes"
    (hermes_home / "logs").mkdir(parents=True)
    with (
        patch("run_agent.get_tool_definitions", return_value=[]),
        patch("run_agent.check_toolset_requirements", return_value={}),
        patch("run_agent.OpenAI"),
        patch("run_agent._hermes_home", hermes_home),
        patch("agent.model_metadata.fetch_model_metadata", return_value={}),
    ):
        agent = AIAgent(
            api_key="test-key",
            base_url="https://openrouter.ai/api/v1",
            quiet_mode=True,
            skip_context_files=True,
            skip_memory=True,
        )

    agent.client = MagicMock()
    agent._cached_system_prompt = "You are helpful."
    agent._use_prompt_caching = False
    agent.compression_enabled = False
    agent.save_trajectories = False
    agent._check_code_skew_before_turn = MagicMock(
        return_value="boot abc1234567, disk def4567890"
    )

    with (
        patch.object(agent, "_persist_session"),
        patch.object(agent, "_save_trajectory"),
        patch.object(agent, "_cleanup_task_resources"),
    ):
        result = agent.run_conversation("hello")

    assert result["completed"] is False
    assert "Please restart the application" in result["final_response"]
    agent.client.chat.completions.create.assert_not_called()
