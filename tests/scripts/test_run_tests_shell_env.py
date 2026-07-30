"""Behavioral coverage for the canonical shell test runner's clean environment."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from tools.environments.local import _find_bash, _windows_to_msys_path


_PROBE_PREFIX = "runner-windows-env-probe:"
_REQUIRED_WINDOWS_ENV = (
    "TEMP",
    "TMP",
    "SYSTEMDRIVE",
    "PROGRAMDATA",
    "COMSPEC",
    "PATHEXT",
)


def test_run_tests_shell_preserves_windows_process_environment(tmp_path):
    marker = os.environ.get("HERMES_RUN_SLOW_PET_TESTS", "")
    if marker.startswith(_PROBE_PREFIX):
        expected_path = Path(marker.removeprefix(_PROBE_PREFIX))
        expected = json.loads(expected_path.read_text(encoding="utf-8"))
        assert {name: os.environ.get(name) for name in expected} == expected
        return

    repo = Path(__file__).resolve().parents[2]
    expected = {
        name: os.environ.get(name) or f"hermes-test-{name.lower()}"
        for name in _REQUIRED_WINDOWS_ENV
    }
    expected_path = tmp_path / "expected-windows-env.json"
    expected_path.write_text(json.dumps(expected), encoding="utf-8")
    env = os.environ.copy()
    env.update(expected)
    env["HERMES_RUN_SLOW_PET_TESTS"] = _PROBE_PREFIX + str(expected_path)

    completed = subprocess.run(
        [
            _find_bash(),
            _windows_to_msys_path(str(repo / "scripts" / "run_tests.sh")),
            _windows_to_msys_path(str(Path(__file__).resolve())),
            "-q",
            "-k",
            "test_run_tests_shell_preserves_windows_process_environment",
        ],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
