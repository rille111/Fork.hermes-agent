"""Tests for explicit terminal inactivity policy and safe environment defaults."""

import os
import time
import pytest
from unittest.mock import MagicMock, patch

from tools.environments.base import (
    _strip_ansi,
    _detect_interactive_prompt,
    _NONINTERACTIVE_ENV_DEFAULTS,
    _BoundedOutputCollector,
    BaseEnvironment,
)
from tools.environments.local import _make_run_env


def test_strip_ansi():
    raw = "\x1b[32mSelect option [1-3]: \x1b[0m"
    assert _strip_ansi(raw) == "Select option [1-3]: "


def test_detect_interactive_prompt():
    # Y/N prompts
    assert _detect_interactive_prompt("Do you want to continue? [Y/n]") is not None
    assert _detect_interactive_prompt("Overwrite file? (y/N) ") is not None

    # Password prompts
    assert _detect_interactive_prompt("[sudo] password for admin:") is not None
    assert _detect_interactive_prompt("Enter passphrase for key '/root/.ssh/id_rsa':") is not None

    # Menu choices
    assert _detect_interactive_prompt("Select an option:") is not None
    assert _detect_interactive_prompt("Enter choice [1-5]:") is not None

    # Press key
    assert _detect_interactive_prompt("Press enter to continue...") is not None

    # Normal output should NOT match
    assert _detect_interactive_prompt("Successfully built 15 targets.") is None
    assert _detect_interactive_prompt("Processing item 42 of 100...") is None


def test_noninteractive_env_defaults():
    # Keep narrow prompt prevention without changing build/test semantics.
    assert _NONINTERACTIVE_ENV_DEFAULTS["DEBIAN_FRONTEND"] == "noninteractive"
    assert _NONINTERACTIVE_ENV_DEFAULTS["GIT_TERMINAL_PROMPT"] == "0"
    assert _NONINTERACTIVE_ENV_DEFAULTS["PIP_NO_INPUT"] == "1"
    assert _NONINTERACTIVE_ENV_DEFAULTS["PYTHONUNBUFFERED"] == "1"
    assert "CI" not in _NONINTERACTIVE_ENV_DEFAULTS
    assert "AUTOMATED_TESTING" not in _NONINTERACTIVE_ENV_DEFAULTS
    assert "NPM_CONFIG_YES" not in _NONINTERACTIVE_ENV_DEFAULTS

    # Verify _make_run_env includes them
    run_env = _make_run_env({})
    assert "CI" not in run_env
    assert "AUTOMATED_TESTING" not in run_env
    assert "NPM_CONFIG_YES" not in run_env
    assert run_env.get("GIT_TERMINAL_PROMPT") == "0"
    assert run_env.get("PIP_NO_INPUT") == "1"


def test_bounded_output_collector_tail():
    collector = _BoundedOutputCollector(max_chars=1000)
    collector.append("Line 1\n")
    collector.append("Line 2\n")
    collector.append("Line 3\n")

    tail = collector.get_tail(chars=15)
    assert "Line 3" in tail
    assert collector.last_update_time > 0


class DummyEnvironment(BaseEnvironment):
    def _run_bash(self, cmd_string, *, login=False, timeout=120, stdin_data=None):
        pass

    def cleanup(self):
        pass


def test_environment_env_injection():
    env = DummyEnvironment(cwd=".", timeout=60, env={"CUSTOM_VAR": "value"})
    assert env.env["CUSTOM_VAR"] == "value"
    assert "CI" not in env.env
    assert "AUTOMATED_TESTING" not in env.env
    assert "NPM_CONFIG_YES" not in env.env
    assert env.env["GIT_TERMINAL_PROMPT"] == "0"


def test_wait_for_process_prompt_detection_when_policy_enabled():
    env = DummyEnvironment(cwd=".", timeout=60)

    # Mock ProcessHandle
    proc = MagicMock()
    proc.poll.return_value = None  # Process is still running
    proc.pid = 12345
    proc.stdout = None

    # Mock output collector returning prompt
    with patch("tools.environments.base._BoundedOutputCollector") as MockCollector:
        mock_collector_inst = MagicMock()
        MockCollector.return_value = mock_collector_inst
        mock_collector_inst.get_tail.return_value = "Do you want to proceed? [y/N]"
        mock_collector_inst.last_update_time = time.monotonic() - 6.0  # 6s idle
        mock_collector_inst.render.side_effect = lambda suffix="": "Do you want to proceed? [y/N]" + suffix

        res = env._wait_for_process(proc, timeout=60, inactivity_timeout=60)
        assert res["returncode"] == 124
        assert "interactive prompt" in res["output"]


def test_wait_for_process_inactivity_timeout():
    env = DummyEnvironment(cwd=".", timeout=60)

    proc = MagicMock()
    proc.poll.return_value = None
    proc.pid = 12345
    proc.stdout = None

    with patch("tools.environments.base._BoundedOutputCollector") as MockCollector:
        mock_collector_inst = MagicMock()
        MockCollector.return_value = mock_collector_inst
        mock_collector_inst.get_tail.return_value = "Building project..."
        mock_collector_inst.last_update_time = time.monotonic() - 15.0  # 15s idle
        mock_collector_inst.render.side_effect = lambda suffix="": "Building project..." + suffix
        res = env._wait_for_process(proc, timeout=60, inactivity_timeout=10)
        assert res["returncode"] == 124
        assert "output inactivity" in res["output"]


def test_zero_inactivity_timeout_does_not_kill_silent_process():
    env = DummyEnvironment(cwd=".", timeout=60)
    proc = MagicMock()
    proc.poll.side_effect = [None, 0, 0]
    proc.pid = 12345
    proc.stdout = None
    proc.returncode = 0
    env._kill_process = MagicMock()

    with patch("tools.environments.base._BoundedOutputCollector") as MockCollector:
        output = MagicMock()
        MockCollector.return_value = output
        output.get_tail.return_value = "Waiting on input..."
        output.last_update_time = time.monotonic() - 30.0
        output.total_chars = 0
        output.render.return_value = "Waiting on input..."

        res = env._wait_for_process(proc, timeout=60, inactivity_timeout=0)

    assert res["returncode"] == 0
    env._kill_process.assert_not_called()
