"""Behavioral coverage for file-tool checkpoint path resolution."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from agent.tool_executor import _ensure_file_checkpoint
from tools.checkpoint_manager import CheckpointManager


def test_relative_file_checkpoint_uses_task_workspace(tmp_path, monkeypatch):
    """Checkpoint lookup must use the same cwd as a relative file mutation."""
    process_cwd = tmp_path / "opt" / "hermes"
    workspace_cwd = tmp_path / "opt" / "data" / "workspace"
    process_cwd.mkdir(parents=True)
    workspace_cwd.mkdir(parents=True)

    # Both directories contain content so checkpointing the wrong one would
    # still succeed and remain observable as the regression did in Docker.
    (process_cwd / "pyproject.toml").write_text("[project]\nname = 'hermes'\n")
    (workspace_cwd / "pyproject.toml").write_text("[project]\nname = 'workspace'\n")
    (workspace_cwd / "existing.txt").write_text("before\n")

    monkeypatch.chdir(process_cwd)
    monkeypatch.setenv("TERMINAL_CWD", str(workspace_cwd))
    monkeypatch.setattr(
        "tools.checkpoint_manager.CHECKPOINT_BASE",
        tmp_path / "checkpoints",
    )

    manager = CheckpointManager(enabled=True)
    agent = SimpleNamespace(_checkpoint_mgr=manager)

    _ensure_file_checkpoint(
        agent,
        "write_file",
        {"path": "test_permissions2.txt"},
        "gateway-session",
    )

    assert manager.list_checkpoints(str(workspace_cwd))
    assert manager.list_checkpoints(str(process_cwd)) == []


def test_v4a_patch_checkpoints_each_affected_workspace(tmp_path, monkeypatch):
    roots = {
        "first.txt": str(tmp_path / "first-workspace"),
        "second.txt": str(tmp_path / "second-workspace"),
    }
    manager = SimpleNamespace(
        get_working_dir_for_path=lambda path: roots[Path(path).name],
        ensure_checkpoint=Mock(),
    )
    agent = SimpleNamespace(_checkpoint_mgr=manager)
    monkeypatch.setattr(
        "tools.file_tools._resolve_path_for_task",
        lambda path, _task_id: tmp_path / path,
    )
    patch_body = "\n".join(
        (
            "*** " + "Begin Patch",
            "*** " + "Update File: first.txt",
            "@@",
            "-before",
            "+after",
            "*** " + "Update File: second.txt",
            "@@",
            "-before",
            "+after",
            "*** " + "End Patch",
        )
    )

    _ensure_file_checkpoint(
        agent,
        "patch",
        {"mode": "patch", "patch": patch_body},
        "gateway-session",
    )

    assert manager.ensure_checkpoint.call_count == 2
    manager.ensure_checkpoint.assert_any_call(roots["first.txt"], "before patch")
    manager.ensure_checkpoint.assert_any_call(roots["second.txt"], "before patch")
