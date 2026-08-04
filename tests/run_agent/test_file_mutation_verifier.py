"""Tests for the per-turn file-mutation verifier footer.

Covers the three moving pieces:

1. ``_extract_file_mutation_targets`` — pulls file paths from write_file /
   patch (replace + V4A) tool-call argument dicts.
2. ``AIAgent._record_file_mutation_result`` — builds the per-turn state
   dict, removing entries when a later success supersedes an earlier
   failure for the same path.
3. ``AIAgent._format_file_mutation_failure_footer`` — renders the dict
   as a user-visible advisory.

Regression target: the "Ben Eng llm-wiki" session where grok-4.1-fast
batched parallel patches, half failed, and the model summarised the
turn claiming every file was edited. The verifier surfaces unresolved
failed file-tool attempts while reconciling later observed content changes
that may have landed through a different tool.
"""

from __future__ import annotations

import json
import os
import stat as stat_module
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from run_agent import (
    AIAgent,
    _FILE_MUTATING_TOOLS,
    _extract_error_preview,
    _extract_file_mutation_targets,
    _extract_landed_file_mutation_paths,
)


# ---------------------------------------------------------------------------
# _extract_file_mutation_targets
# ---------------------------------------------------------------------------


class TestExtractFileMutationTargets:
    def test_non_mutating_tool_returns_empty(self):
        assert _extract_file_mutation_targets("read_file", {"path": "/x"}) == []
        assert _extract_file_mutation_targets("terminal", {"command": "ls"}) == []



    def test_patch_replace_mode_returns_path(self):
        args = {"mode": "replace", "path": "/tmp/a.md", "old_string": "x", "new_string": "y"}
        assert _extract_file_mutation_targets("patch", args) == ["/tmp/a.md"]



    def test_patch_v4a_header_without_space_matches_runtime_parser(self):
        marker = "*" * 3
        body = (
            f"{marker} Begin Patch\n"
            f"{marker}Update File: /tmp/a.md\n"
            "@@\n-old\n+new\n"
            f"{marker} End Patch\n"
        )

        assert _extract_file_mutation_targets(
            "patch", {"mode": "patch", "patch": body}
        ) == ["/tmp/a.md"]

    def test_patch_v4a_split_move_destination_matches_runtime_parser(self):
        body = (
            "*** Begin Patch\n"
            "*** Move File: /tmp/source.md ->\n"
            "/tmp/ghost.md\n"
            "*** End Patch\n"
        )

        assert _extract_file_mutation_targets(
            "patch", {"mode": "patch", "patch": body}
        ) == []

    def test_patch_v4a_multi_file(self):
        body = (
            "*** Begin Patch\n"
            "*** Update File: /tmp/a.md\n"
            "@@ @@\n-a\n+b\n"
            "*** Add File: /tmp/new.md\n"
            "+fresh\n"
            "*** Delete File: /tmp/old.md\n"
            "*** End Patch\n"
        )
        args = {"mode": "patch", "patch": body}
        paths = _extract_file_mutation_targets("patch", args)
        assert paths == ["/tmp/a.md", "/tmp/new.md", "/tmp/old.md"]


    def test_patch_v4a_accepts_no_space_after_asterisks(self):
        """Match patch_parser / file_tools: ``***Update File:`` (no space)."""
        body = "***Update File: nospace.py\n"
        assert _extract_file_mutation_targets(
            "patch", {"mode": "patch", "patch": body}
        ) == ["nospace.py"]


# ---------------------------------------------------------------------------
# _extract_error_preview
# ---------------------------------------------------------------------------


class TestExtractErrorPreview:
    def test_json_error_field_preferred(self):
        raw = json.dumps({"success": False, "error": "Could not find old_string in /tmp/x"})
        assert _extract_error_preview(raw) == "Could not find old_string in /tmp/x"

    def test_plain_string_falls_through(self):
        assert _extract_error_preview("Error executing tool: boom") == "Error executing tool: boom"

    def test_long_preview_truncated(self):
        long = "x" * 500
        out = _extract_error_preview(long, max_len=50)
        assert len(out) <= 50
        assert out.endswith("…")



# ---------------------------------------------------------------------------
# _record_file_mutation_result — state transitions
# ---------------------------------------------------------------------------


def _bare_agent() -> AIAgent:
    """Skip __init__ and only attach the per-turn state dict.

    AIAgent.__init__ takes ~60 parameters and touches network, auth, and
    the filesystem.  For these tests we only need the two methods —
    ``_record_file_mutation_result`` and ``_format_file_mutation_failure_footer``.
    Using ``object.__new__`` mirrors the gateway-test pattern documented in
    the agent pitfalls list.
    """
    agent = object.__new__(AIAgent)
    agent._turn_failed_file_mutations = {}
    agent._turn_file_mutation_paths = set()
    return agent



def _mutation_entries(state: dict, path: str) -> list[dict]:
    """Return ledger entries whose display/key path matches *path*."""
    out = []
    for key, info in state.items():
        display = info.get("_display_path") if isinstance(info, dict) else None
        if display == path or key == path or str(key).endswith(":" + path) or str(key).endswith(path):
            out.append(info if isinstance(info, dict) else {"_key": key})
    return out


def _has_mutation(state: dict, path: str) -> bool:
    return bool(_mutation_entries(state, path))


def _mutation_entry(state: dict, path: str) -> dict:
    entries = _mutation_entries(state, path)
    assert entries, f"expected mutation entry for {path!r} in {list(state)}"
    return entries[0]


class TestRecordFileMutationResult:
    def test_non_mutating_tool_ignored(self):
        agent = _bare_agent()
        agent._record_file_mutation_result(
            "read_file", {"path": "/tmp/x"}, "{}", is_error=True,
        )
        assert agent._turn_failed_file_mutations == {}

    def test_failure_recorded(self):
        agent = _bare_agent()
        result = json.dumps({"success": False, "error": "Could not find old_string"})
        agent._record_file_mutation_result(
            "patch", {"mode": "replace", "path": "/tmp/a.md", "old_string": "x", "new_string": "y"},
            result, is_error=True,
        )
        state = agent._turn_failed_file_mutations
        assert _has_mutation(state, "/tmp/a.md")
        assert _mutation_entry(state, "/tmp/a.md")["tool"] == "patch"
        assert "Could not find old_string" in _mutation_entry(state, "/tmp/a.md")["error_preview"]

    def test_success_removes_prior_failure(self):
        agent = _bare_agent()
        # First attempt fails
        agent._record_file_mutation_result(
            "patch", {"mode": "replace", "path": "/tmp/a.md", "old_string": "x", "new_string": "y"},
            json.dumps({"error": "not found"}), is_error=True,
        )
        assert _has_mutation(agent._turn_failed_file_mutations, "/tmp/a.md")
        # Second attempt with corrected old_string succeeds
        agent._record_file_mutation_result(
            "patch", {"mode": "replace", "path": "/tmp/a.md", "old_string": "real", "new_string": "fixed"},
            json.dumps({"success": True, "diff": "..."}), is_error=False,
        )
        assert agent._turn_failed_file_mutations == {}
        assert agent._turn_file_mutation_paths == {"/tmp/a.md"}

    def test_non_landed_non_error_result_does_not_clear_prior_failure(self):
        agent = _bare_agent()
        args = {
            "mode": "replace",
            "path": "/tmp/a.md",
            "old_string": "x",
            "new_string": "y",
        }
        agent._record_file_mutation_result(
            "patch",
            args,
            json.dumps({"error": "not found"}),
            is_error=True,
        )

        agent._record_file_mutation_result(
            "patch",
            args,
            "SKIPPED_BY_EXECUTION_MIDDLEWARE",
            is_error=False,
        )

        assert _has_mutation(agent._turn_failed_file_mutations, "/tmp/a.md")

    def test_external_write_after_failure_suppresses_false_footer(self, tmp_path):
        """A non-file tool may recover a failed patch through an official CLI.

        The verifier must inspect the final on-disk state instead of claiming
        the file was not modified merely because the successful recovery did
        not go through ``write_file`` or ``patch``.
        """
        target = tmp_path / "config.yaml"
        target.write_text("before\n", encoding="utf-8")
        agent = _bare_agent()

        agent._record_file_mutation_result(
            "patch",
            {
                "mode": "replace",
                "path": str(target),
                "old_string": "before",
                "new_string": "after",
            },
            json.dumps({"error": "protected config; use hermes config set"}),
            is_error=True,
        )
        target.write_text("after\n", encoding="utf-8")

        footer = agent._format_file_mutation_failure_footer(
            agent._turn_failed_file_mutations,
        )

        assert footer == ""

    def test_failure_after_external_write_still_warns(self, tmp_path):
        target = tmp_path / "config.yaml"
        target.write_text("before\n", encoding="utf-8")
        agent = _bare_agent()
        args = {
            "mode": "replace",
            "path": str(target),
            "old_string": "before",
            "new_string": "after",
        }

        agent._record_file_mutation_result(
            "patch", args, json.dumps({"error": "first failure"}), is_error=True,
        )
        target.write_text("changed elsewhere\n", encoding="utf-8")
        agent._record_file_mutation_result(
            "patch", args, json.dumps({"error": "second failure"}), is_error=True,
        )

        footer = agent._format_file_mutation_failure_footer(
            agent._turn_failed_file_mutations,
        )

        assert "unresolved failed file-tool mutations for 1 file(s)" in footer
        assert "first failure" in footer

    def test_metadata_only_change_does_not_count_as_recovery(self, tmp_path):
        target = tmp_path / "config.yaml"
        target.write_text("unchanged\n", encoding="utf-8")
        agent = _bare_agent()
        agent._record_file_mutation_result(
            "patch",
            {"mode": "replace", "path": str(target)},
            json.dumps({"error": "failed"}),
            is_error=True,
        )

        before = target.stat()
        os.utime(
            target,
            ns=(before.st_atime_ns, before.st_mtime_ns + 2_000_000_000),
        )

        footer = agent._format_file_mutation_failure_footer(
            agent._turn_failed_file_mutations,
        )
        assert "unresolved failed file-tool mutations for 1 file(s)" in footer

    def test_interrupted_turn_preserves_footer(self, monkeypatch):
        from agent.turn_finalizer import finalize_turn
        import uuid

        agent = _bare_agent()
        agent.max_iterations = 5
        agent.iteration_budget = type("Budget", (), {"remaining": 5, "used": 0, "max_total": 5})()
        agent.model = "test-model"
        agent.provider = "test-provider"
        agent.base_url = "test-url"
        agent.session_input_tokens = 0
        agent.session_output_tokens = 0
        agent.session_cache_read_tokens = 0
        agent.session_cache_write_tokens = 0
        agent.session_reasoning_tokens = 0
        agent.session_prompt_tokens = 0
        agent.session_completion_tokens = 0
        agent.session_total_tokens = 0
        agent.session_estimated_cost_usd = 0.0
        agent.session_cost_status = ""
        agent.session_cost_source = ""
        agent.save_trajectories = False
        agent.context_compressor = None
        agent._tool_guardrail_halt_decision = None
        agent._interrupt_message = None
        agent._execution_thread_id = None
        agent._session_db = None
        agent.session_id = "test-session"
        agent._turn_failed_file_mutations = {
            "config.yaml": {
                "tool": "patch",
                "error_preview": "failed",
                "disk_snapshot": None,
                "turn_id": "test",
                "task_id": "default",
            }
        }
        agent._current_task_id = "default"
        agent._file_mutation_verifier_enabled = lambda: True
        agent._format_file_mutation_failure_footer = lambda _failed: "MOCKED FOOTER"
        agent._skill_nudge_interval = 0
        agent._memory_manager = None

        result = finalize_turn(
            agent=agent,
            final_response="Interrupted early",
            api_call_count=1,
            interrupted=True,
            failed=False,
            messages=[{"role": "user", "content": "hi"}],
            conversation_history=[],
            effective_task_id="default",
            turn_id="test",
            user_message="hi",
            original_user_message="hi",
            _should_review_memory=False,
            _turn_exit_reason="interrupted",
        )

        response = result.get("final_response", "")
        assert "Interrupted early" in response
        assert "MOCKED FOOTER" in response

    def test_empty_turn_preserves_footer(self, monkeypatch):
        from agent.turn_finalizer import finalize_turn

        agent = _bare_agent()
        agent.max_iterations = 5
        agent.iteration_budget = type("Budget", (), {"remaining": 5, "used": 0, "max_total": 5})()
        agent.model = "test-model"
        agent.provider = "test-provider"
        agent.base_url = "test-url"
        agent.session_input_tokens = 0
        agent.session_output_tokens = 0
        agent.session_cache_read_tokens = 0
        agent.session_cache_write_tokens = 0
        agent.session_reasoning_tokens = 0
        agent.session_prompt_tokens = 0
        agent.session_completion_tokens = 0
        agent.session_total_tokens = 0
        agent.session_estimated_cost_usd = 0.0
        agent.session_cost_status = ""
        agent.session_cost_source = ""
        agent.save_trajectories = False
        agent.context_compressor = None
        agent._tool_guardrail_halt_decision = None
        agent._interrupt_message = None
        agent._execution_thread_id = None
        agent._session_db = None
        agent.session_id = "test-session"
        agent._turn_failed_file_mutations = {
            "config.yaml": {
                "tool": "patch",
                "error_preview": "failed",
                "disk_snapshot": None,
                "turn_id": "test",
                "task_id": "default",
            }
        }
        agent._current_task_id = "default"
        agent._file_mutation_verifier_enabled = lambda: True
        agent._format_file_mutation_failure_footer = lambda _failed: "MOCKED FOOTER"
        agent._skill_nudge_interval = 0
        agent._memory_manager = None
        agent._turn_completion_explainer_enabled = lambda: True
        agent._format_turn_completion_explanation = lambda _r: "EMPTY EXPL"

        result = finalize_turn(
            agent=agent,
            final_response="",
            api_call_count=1,
            interrupted=False,
            failed=False,
            messages=[{"role": "user", "content": "hi"}],
            conversation_history=[],
            effective_task_id="default",
            turn_id="test",
            user_message="hi",
            original_user_message="hi",
            _should_review_memory=False,
            _turn_exit_reason="empty_response",
        )

        response = result.get("final_response", "")
        assert "EMPTY EXPL" in response
        assert "MOCKED FOOTER" in response

    def test_signature_does_not_open_non_regular_targets(self, monkeypatch):
        reads = []
        closes = []
        monkeypatch.setattr(
            "run_agent.os",
            SimpleNamespace(
                O_RDONLY=0,
                O_BINARY=0,
                O_NONBLOCK=0,
                O_NOFOLLOW=0,
                name="posix",
                path=os.path,
                sep=os.sep,
                lstat=lambda _path: SimpleNamespace(
                    st_mode=stat_module.S_IFDIR,
                    st_file_attributes=0,
                ),
                open=lambda _path, _flags: 41,
                fstat=lambda _fd: SimpleNamespace(
                    st_mode=stat_module.S_IFIFO,
                    st_size=0,
                ),
                read=lambda *_args: reads.append(_args),
                close=lambda fd: closes.append(fd),
            ),
        )
        assert AIAgent._file_mutation_disk_signature("named-pipe") is None
        assert reads == []
        assert closes == [41]

    def test_signature_does_not_hash_oversized_targets(self, monkeypatch):
        reads = []
        closes = []
        monkeypatch.setattr(
            "run_agent.os",
            SimpleNamespace(
                O_RDONLY=0,
                O_BINARY=0,
                O_NONBLOCK=0,
                O_NOFOLLOW=0,
                name="posix",
                path=os.path,
                sep=os.sep,
                lstat=lambda _path: SimpleNamespace(
                    st_mode=stat_module.S_IFDIR,
                    st_file_attributes=0,
                ),
                open=lambda _path, _flags: 42,
                fstat=lambda _fd: SimpleNamespace(
                    st_mode=stat_module.S_IFREG,
                    st_size=1024 * 1024 + 1,
                ),
                read=lambda *_args: reads.append(_args),
                close=lambda fd: closes.append(fd),
            ),
        )
        assert AIAgent._file_mutation_disk_signature("huge-file") is None
        assert reads == []
        assert closes == [42]

    def test_signature_rejects_torn_content_reads(self, monkeypatch):
        stat_result = SimpleNamespace(
            st_mode=stat_module.S_IFREG | 0o644,
            st_size=4,
            st_dev=1,
            st_ino=2,
            st_mtime_ns=3,
            st_ctime_ns=4,
        )
        fake_os = SimpleNamespace(
            name="posix",
            O_RDONLY=0,
            O_BINARY=0,
            O_NONBLOCK=0,
            O_NOFOLLOW=0,
            O_NOINHERIT=0,
            SEEK_SET=0,
            path=os.path,
            sep=os.sep,
            lstat=MagicMock(return_value=SimpleNamespace(
                st_mode=stat_module.S_IFDIR,
                st_file_attributes=0,
            )),
            open=MagicMock(return_value=41),
            fstat=MagicMock(return_value=stat_result),
            # First pass observes mixed bytes; second sees stable final
            # content. A one-pass digest would look like a later mutation.
            read=MagicMock(side_effect=[b"AA", b"BB", b"", b"AAAA", b""]),
            lseek=MagicMock(return_value=0),
            close=MagicMock(),
        )
        monkeypatch.setattr("run_agent.os", fake_os)

        assert AIAgent._file_mutation_disk_signature("/tmp/target") is None
        assert fake_os.close.call_args_list == [((41,),)]
        assert fake_os.lseek.call_count == 2

    def test_signature_open_is_time_bounded(self, monkeypatch):
        def blocked_open(_path, _flags):
            time.sleep(0.75)
            raise FileNotFoundError

        monkeypatch.setattr("run_agent.os.open", blocked_open)
        started = time.monotonic()

        assert AIAgent._file_mutation_disk_signature("offline-share") is None
        assert time.monotonic() - started < 0.6

    def test_local_path_resolution_is_time_bounded(self, monkeypatch):
        def blocked_resolve(_path, _task_id):
            time.sleep(0.75)
            return "/offline/share/config.yaml"

        monkeypatch.setattr(
            "tools.file_tools._terminal_env_type_for_task_strict",
            lambda _task_id: "local",
        )
        monkeypatch.setattr(
            "tools.file_tools._resolve_local_path_for_task_lexically",
            blocked_resolve,
        )
        started = time.monotonic()

        assert AIAgent._resolved_file_mutation_target_path("config.yaml") is None
        assert time.monotonic() - started < 0.6

    def test_sensitive_path_is_denied_before_target_io(self, monkeypatch):
        events = []
        monkeypatch.setattr(
            "tools.file_tools._terminal_env_type_for_task_strict",
            lambda _task_id: events.append("backend") or "local",
        )
        monkeypatch.setattr(
            "tools.file_tools._resolve_local_path_for_task_lexically",
            lambda _path, _task_id: events.append("lexical") or "/tmp/blocked",
        )
        monkeypatch.setattr(
            "agent.file_safety.get_file_verifier_block_error",
            lambda _path: events.append("sensitive") or "blocked",
        )

        assert AIAgent._resolved_file_mutation_target_path_sync(
            "/home/u/.ssh/id_rsa",
            "task-a",
        ) is None
        assert events == ["backend", "lexical", "sensitive"]

    def test_backend_lookup_failure_does_not_resolve_on_host(self, monkeypatch):
        resolved = []
        monkeypatch.setattr(
            "tools.file_tools._detect_terminal_env_type_for_task",
            lambda _task_id: (_ for _ in ()).throw(RuntimeError("unavailable")),
        )
        monkeypatch.setattr(
            "tools.file_tools._resolve_path_for_task",
            lambda path, _task_id: resolved.append(path) or path,
        )

        assert AIAgent._resolved_file_mutation_target_path_sync(
            "/workspace/config.yaml",
            "uncertain-task",
        ) is None
        assert resolved == []

    def test_local_verifier_resolution_is_lexical_and_task_relative(
        self,
        monkeypatch,
        tmp_path,
    ):
        workspace = tmp_path / "workspace"
        monkeypatch.setattr(
            "tools.file_tools._terminal_env_type_for_task_strict",
            lambda _task_id: "local",
        )
        monkeypatch.setattr(
            "tools.file_tools._authoritative_workspace_root",
            lambda _task_id: str(workspace),
        )
        monkeypatch.setattr(
            "tools.file_tools._resolve_path_for_task",
            lambda *_args: pytest.fail("verifier must not dereference the target"),
        )

        resolved = AIAgent._resolved_file_mutation_target_path_sync(
            "nested/config.yaml",
            "task-a",
        )

        assert resolved == os.path.normpath(str(workspace / "nested" / "config.yaml"))

    def test_signature_rechecks_sensitive_path_before_open(self, monkeypatch):
        events = []
        monkeypatch.setattr(
            "agent.file_safety.get_file_verifier_block_error",
            lambda _path: events.append("sensitive") or "blocked",
        )
        monkeypatch.setattr(
            "run_agent.os.open",
            lambda *_args: events.append("open") or 41,
        )

        assert AIAgent._file_mutation_disk_signature_sync(
            "/home/u/.ssh/id_rsa",
        ) is None
        assert events == ["sensitive"]

    def test_link_or_reparse_component_blocks_signature_open(self, monkeypatch):
        events = []
        monkeypatch.setattr(
            "agent.file_safety.get_file_verifier_block_error",
            lambda _path: None,
        )
        monkeypatch.setattr(
            AIAgent,
            "_file_mutation_path_has_link_component",
            staticmethod(lambda _path: events.append("link-check") or True),
        )
        monkeypatch.setattr(
            "run_agent.os.open",
            lambda *_args: events.append("open") or 41,
        )

        assert AIAgent._file_mutation_disk_signature_sync("safe-looking.txt") is None
        assert events == ["link-check"]

    def test_link_component_detector_rejects_reparse_attributes(self, monkeypatch):
        ordinary = SimpleNamespace(
            st_mode=stat_module.S_IFDIR,
            st_file_attributes=0,
        )
        reparse = SimpleNamespace(
            st_mode=stat_module.S_IFDIR,
            st_file_attributes=0x400,
        )
        monkeypatch.setattr(
            "run_agent.os.lstat",
            lambda path: reparse if str(path).endswith("linked") else ordinary,
        )

        assert AIAgent._file_mutation_path_has_link_component(
            os.path.join(os.getcwd(), "safe", "linked", "target.txt"),
        ) is True

    def test_timed_signature_workers_are_process_bounded(self, monkeypatch):
        release = threading.Event()
        started = 0
        started_lock = threading.Lock()

        def blocked_signature(_path):
            nonlocal started
            with started_lock:
                started += 1
            release.wait(timeout=5)
            return None

        monkeypatch.setattr(
            AIAgent,
            "_file_mutation_disk_signature_sync",
            staticmethod(blocked_signature),
        )
        monkeypatch.setattr(
            "run_agent._FILE_MUTATION_SIGNATURE_TIMEOUT_SECONDS",
            0.01,
        )
        try:
            for index in range(15):
                assert AIAgent._file_mutation_disk_signature(
                    f"blocked-{index}",
                ) is None

            matching = [
                thread
                for thread in threading.enumerate()
                if thread.name.startswith("file-mutation-")
            ]
            assert started <= 10
            assert len(matching) <= 10
        finally:
            release.set()

    def test_timed_signature_admission_does_not_grow_executor_queue(
        self,
        monkeypatch,
    ):
        from tools.daemon_pool import DaemonThreadPoolExecutor

        release = threading.Event()
        executor = DaemonThreadPoolExecutor(
            max_workers=2,
            thread_name_prefix="file-mutation-admission-test",
        )

        def blocked_signature(_path):
            release.wait(timeout=5)
            return None

        monkeypatch.setattr(
            AIAgent,
            "_file_mutation_disk_signature_sync",
            staticmethod(blocked_signature),
        )
        monkeypatch.setattr(
            "run_agent._FILE_MUTATION_SIGNATURE_TIMEOUT_SECONDS",
            0.005,
        )
        monkeypatch.setattr("run_agent._FILE_MUTATION_IO_EXECUTOR", executor)
        monkeypatch.setattr(
            "run_agent._FILE_MUTATION_IO_ADMISSION",
            threading.BoundedSemaphore(2),
            raising=False,
        )
        try:
            for index in range(20):
                assert AIAgent._file_mutation_disk_signature(
                    f"blocked-admission-{index}",
                ) is None

            assert executor._work_queue.qsize() <= 2
        finally:
            release.set()
            executor.shutdown(wait=True)

    def test_snapshot_skips_ssh_backend_without_resolving_on_host(
        self,
        monkeypatch,
        tmp_path,
    ):
        target = tmp_path / "remote-looking.yaml"
        target.write_text("remote content\n", encoding="utf-8")
        resolved = []

        monkeypatch.setattr(
            "tools.file_tools._terminal_env_type_for_task_strict",
            lambda _task_id: "ssh",
        )

        def track_resolve(path, _task_id):
            resolved.append(path)
            return target

        monkeypatch.setattr(
            "tools.file_tools._resolve_path_for_task",
            track_resolve,
        )

        assert AIAgent._snapshot_file_mutation_target(
            "/home/user/remote-looking.yaml",
            "ssh-task",
        ) is None
        assert resolved == []

    @pytest.mark.parametrize(
        "unsafe_path",
        [
            r"\\server\share\config.yaml",
            r"\\?\UNC\server\share\config.yaml",
            r"\\?\GLOBALROOT\Device\NamedPipe\blocked",
            r"\\?\C:\work\config.yaml",
            r"\\.\pipe\blocked",
            r"NUL.txt",
            r"C:\work\CON",
            r"C:\work\COM1.log",
            r"C:\work\AUX .txt",
            r"Z:dir\file.md",
        ],
    )
    def test_snapshot_rejects_windows_network_and_device_namespaces_before_resolving(
        self,
        monkeypatch,
        unsafe_path,
    ):
        resolved = []
        monkeypatch.setattr("run_agent.os", SimpleNamespace(name="nt"))
        monkeypatch.setattr(
            "tools.file_tools._terminal_env_type_for_task_strict",
            lambda _task_id: "local",
        )
        monkeypatch.setattr(
            "tools.file_tools._resolve_path_for_task",
            lambda path, _task_id: resolved.append(path) or path,
        )

        assert AIAgent._resolved_file_mutation_target_path(unsafe_path) is None
        assert resolved == []

    def test_snapshot_skips_read_denied_credential_files(
        self,
        monkeypatch,
        tmp_path,
    ):
        hermes_home = tmp_path / "hermes-home"
        target = hermes_home / ".env"
        target.parent.mkdir()
        target.write_text("SECRET=value\n", encoding="utf-8")
        monkeypatch.setenv("HERMES_HOME", str(hermes_home))
        monkeypatch.setattr(
            "tools.file_tools._terminal_env_type_for_task_strict",
            lambda _task_id: "local",
        )
        monkeypatch.setattr(
            "tools.file_tools._resolve_path_for_task",
            lambda _path, _task_id: target,
        )

        assert AIAgent._resolved_file_mutation_target_path(str(target)) is None

    def test_snapshot_skips_every_target_rejected_by_verifier_policy(
        self,
        monkeypatch,
        tmp_path,
    ):
        target = tmp_path / "blocked.yaml"
        target.write_text("do not inspect\n", encoding="utf-8")
        monkeypatch.setattr(
            "tools.file_tools._terminal_env_type_for_task_strict",
            lambda _task_id: "local",
        )
        monkeypatch.setattr(
            "tools.file_tools._resolve_local_path_for_task_lexically",
            lambda _path, _task_id: target,
        )
        monkeypatch.setattr(
            "agent.file_safety.get_file_verifier_block_error",
            lambda _path: "blocked",
        )

        assert AIAgent._resolved_file_mutation_target_path(str(target)) is None

    def test_success_records_declared_paths_for_verify_on_stop(self):
        agent = _bare_agent()

        agent._record_file_mutation_result(
            "write_file",
            {"path": "a.py", "content": "print('ok')\n"},
            json.dumps({"bytes_written": 12, "files_modified": ["/tmp/project/a.py"]}),
            is_error=False,
        )

        assert agent._turn_file_mutation_paths == {"a.py"}

    def test_landed_paths_ignore_undeclared_tool_result_paths(self):
        paths = _extract_landed_file_mutation_paths(
            "patch",
            {"mode": "replace", "path": "src/app.py"},
            json.dumps({
                "success": True,
                "files_modified": ["/tmp/project/src/app.py"],
            }),
        )

        assert paths == ["src/app.py"]

    def test_reported_landed_path_cannot_clear_or_register_undeclared_target(self):
        agent = _bare_agent()
        agent._record_file_mutation_result(
            "write_file",
            {"path": "b.py", "content": "old"},
            json.dumps({"error": "failed"}),
            True,
            failure_snapshots={"b.py": None},
        )

        agent._record_file_mutation_result(
            "write_file",
            {"path": "a.py", "content": "new"},
            json.dumps({"bytes_written": 3, "files_modified": ["b.py"]}),
            False,
        )

        assert _has_mutation(agent._turn_failed_file_mutations, "b.py")
        assert agent._turn_file_mutation_paths == {"a.py"}

    def test_write_file_with_lint_error_counts_as_landed(self):
        agent = _bare_agent()
        agent._record_file_mutation_result(
            "write_file",
            {"path": "/tmp/a.py", "content": "bad"},
            json.dumps({"error": "write failed"}),
            is_error=True,
        )
        assert _has_mutation(agent._turn_failed_file_mutations, "/tmp/a.py")

        result = json.dumps({
            "bytes_written": 24,
            "lint": {"status": "error", "output": "SyntaxError: invalid syntax"},
        })

        agent._record_file_mutation_result(
            "write_file",
            {"path": "/tmp/a.py", "content": "def nope(:\n"},
            result,
            is_error=True,
        )

        assert agent._turn_failed_file_mutations == {}

    def test_patch_with_lsp_diagnostics_counts_as_landed(self):
        agent = _bare_agent()
        agent._record_file_mutation_result(
            "patch",
            {"mode": "replace", "path": "/tmp/a.py", "old_string": "x", "new_string": "y"},
            json.dumps({"error": "Could not find old_string"}),
            is_error=True,
        )
        assert _has_mutation(agent._turn_failed_file_mutations, "/tmp/a.py")

        result = json.dumps({
            "success": True,
            "diff": "--- a/tmp.py\n+++ b/tmp.py\n",
            "files_modified": ["/tmp/a.py"],
            "lsp_diagnostics": "<diagnostics>ERROR [1:1] type mismatch</diagnostics>",
        })

        agent._record_file_mutation_result(
            "patch",
            {"mode": "replace", "path": "/tmp/a.py", "old_string": "x", "new_string": "y"},
            result,
            is_error=True,
        )

        assert agent._turn_failed_file_mutations == {}

    def test_repeated_failure_keeps_first_error(self):
        agent = _bare_agent()
        agent._record_file_mutation_result(
            "patch", {"mode": "replace", "path": "/tmp/a.md", "old_string": "v1", "new_string": "y"},
            json.dumps({"error": "first error"}), is_error=True,
        )
        agent._record_file_mutation_result(
            "patch", {"mode": "replace", "path": "/tmp/a.md", "old_string": "v2", "new_string": "y"},
            json.dumps({"error": "second error"}), is_error=True,
        )
        # Keep the original error — swapping to the latest would obscure
        # the initial root cause.
        assert "first error" in _mutation_entry(agent._turn_failed_file_mutations, "/tmp/a.md")["error_preview"]

    def test_v4a_multi_file_all_tracked(self):
        agent = _bare_agent()
        body = (
            "*** Begin Patch\n"
            "*** Update File: /tmp/a.md\n@@ @@\n-a\n+b\n"
            "*** Update File: /tmp/b.md\n@@ @@\n-a\n+b\n"
            "*** End Patch\n"
        )
        agent._record_file_mutation_result(
            "patch", {"mode": "patch", "patch": body},
            json.dumps({"error": "parse failure"}), is_error=True,
        )
        assert len(agent._turn_failed_file_mutations) == 2
        assert _has_mutation(agent._turn_failed_file_mutations, "/tmp/a.md")
        assert _has_mutation(agent._turn_failed_file_mutations, "/tmp/b.md")

    @staticmethod
    def _repeated_target_patch_body() -> str:
        marker = "*** "
        return (
            marker + "Begin Patch\n"
            + marker + "Update File: /tmp/repeated.md\n@@ @@\n-a\n+b\n"
            + marker + "Update File: /tmp/repeated.md\n@@ @@\n-b\n+c\n"
            + marker + "Update File: /tmp/repeated.md\n@@ @@\n-c\n+d\n"
            + marker + "End Patch\n"
        )

    def test_repeated_v4a_target_snapshotted_once_during_record(self):
        agent = _bare_agent()
        snapshot_calls = []
        agent._resolved_file_mutation_target_path = lambda path, _task_id: path
        agent._snapshot_resolved_file_mutation_target = (
            lambda path: snapshot_calls.append(path) or None
        )

        agent._record_file_mutation_result(
            "patch",
            {"mode": "patch", "patch": self._repeated_target_patch_body()},
            json.dumps({"error": "parse failure"}),
            is_error=True,
        )

        assert snapshot_calls == ["/tmp/repeated.md"]

    def test_repeated_v4a_target_snapshotted_once_in_worker(self):
        agent = _bare_agent()
        snapshot_calls = []
        agent._resolved_file_mutation_target_path = lambda path, _task_id: path
        agent._snapshot_resolved_file_mutation_target = (
            lambda path: snapshot_calls.append(path) or None
        )

        snapshots = agent._snapshot_failed_file_mutation_targets(
            "patch",
            {"mode": "patch", "patch": self._repeated_target_patch_body()},
            json.dumps({"error": "parse failure"}),
            is_error=True,
        )

        assert snapshot_calls == ["/tmp/repeated.md"]
        assert list(snapshots) == ["/tmp/repeated.md"]

    def test_alias_targets_share_one_resolved_snapshot(self):
        agent = _bare_agent()
        snapshot_calls = []
        aliases = [
            "/tmp/project/config.yaml",
            "/tmp/project/./config.yaml",
            "/tmp/project/subdir/../config.yaml",
        ]
        canonical = "/tmp/project/config.yaml"
        agent._resolved_file_mutation_target_path = (
            lambda _path, _task_id: canonical
        )
        shared_snapshot = {
            "path": canonical,
            "signature": ("present", 1, b"digest"),
        }
        agent._snapshot_resolved_file_mutation_target = (
            lambda path: snapshot_calls.append(path) or shared_snapshot
        )
        marker = "*** "
        body = marker + "Begin Patch\n"
        for path in aliases:
            body += marker + f"Update File: {path}\n@@ @@\n-a\n+b\n"
        body += marker + "End Patch\n"

        snapshots = agent._snapshot_failed_file_mutation_targets(
            "patch",
            {"mode": "patch", "patch": body},
            json.dumps({"error": "parse failure"}),
            is_error=True,
        )

        assert snapshot_calls == [aliases[0]]
        assert list(snapshots) == aliases
        assert all(snapshot is shared_snapshot for snapshot in snapshots.values())

    def test_alias_targets_share_one_ledger_entry(self, tmp_path):
        agent = _bare_agent()
        target = tmp_path / "config.yaml"
        target.write_text("before\n", encoding="utf-8")
        aliases = [str(target)] + [
            str(target.parent / f"subdir-{index}" / ".." / target.name)
            for index in range(10)
        ]
        marker = "*** "
        body = marker + "Begin Patch\n"
        for path in aliases:
            body += marker + f"Update File: {path}\n@@ @@\n-a\n+b\n"
        body += marker + "End Patch\n"

        agent._record_file_mutation_result(
            "patch",
            {"mode": "patch", "patch": body},
            json.dumps({"error": "failed"}),
            True,
        )

        assert len(agent._turn_failed_file_mutations) == 1

    def test_remote_lexical_success_alias_clears_failure(self, monkeypatch):
        agent = _bare_agent()
        monkeypatch.setattr(
            "tools.file_tools._terminal_env_type_for_task_strict",
            lambda _task_id: "ssh",
        )
        agent._record_file_mutation_result(
            "write_file",
            {"path": "subdir/../config.yaml", "content": "new"},
            json.dumps({"error": "failed"}),
            True,
            task_id="remote-task",
        )
        agent._record_file_mutation_result(
            "write_file",
            {"path": "config.yaml", "content": "new"},
            json.dumps({"bytes_written": 1, "path": "config.yaml"}),
            False,
            task_id="remote-task",
        )

        assert agent._turn_failed_file_mutations == {}

    def test_shared_remote_authority_clears_across_task_ids(self, monkeypatch):
        agent = _bare_agent()
        monkeypatch.setattr(
            "tools.file_tools._terminal_env_type_for_task_strict",
            lambda _task_id: "ssh",
        )
        monkeypatch.setattr(
            "tools.terminal_tool._resolve_container_task_id",
            lambda _task_id: "default",
        )
        monkeypatch.setattr(
            "tools.file_tools._authoritative_workspace_root",
            lambda _task_id: "/workspace/shared",
        )

        agent._record_file_mutation_result(
            "write_file",
            {"path": "subdir/../config.yaml", "content": "new"},
            json.dumps({"error": "task A failed"}),
            True,
            task_id="remote-task-a",
        )
        agent._record_file_mutation_result(
            "write_file",
            {"path": "config.yaml", "content": "new"},
            json.dumps({"bytes_written": 1, "path": "config.yaml"}),
            False,
            task_id="remote-task-b",
        )

        assert agent._turn_failed_file_mutations == {}

    def test_posix_remote_backslash_name_does_not_alias_separator(self, monkeypatch):
        agent = _bare_agent()
        monkeypatch.setattr(
            "tools.file_tools._terminal_env_type_for_task_strict",
            lambda _task_id: "ssh",
        )
        monkeypatch.setattr(
            "tools.terminal_tool._resolve_container_task_id",
            lambda _task_id: "shared-authority",
        )
        monkeypatch.setattr(
            "tools.file_tools._authoritative_workspace_root",
            lambda _task_id: "/workspace",
        )

        agent._record_file_mutation_result(
            "write_file",
            {"path": r"dir\file.txt", "content": "old"},
            json.dumps({"error": "failed"}),
            True,
            task_id="task-a",
            failure_snapshots={r"dir\file.txt": None},
        )
        agent._record_file_mutation_result(
            "write_file",
            {"path": "dir/file.txt", "content": "new"},
            json.dumps({"bytes_written": 3, "path": "dir/file.txt"}),
            False,
            task_id="task-b",
        )

        assert _has_mutation(agent._turn_failed_file_mutations, r"dir\file.txt")

    def test_shared_remote_authority_preserves_distinct_workspaces(
        self,
        monkeypatch,
    ):
        agent = _bare_agent()
        monkeypatch.setattr(
            "tools.file_tools._terminal_env_type_for_task_strict",
            lambda _task_id: "ssh",
        )
        monkeypatch.setattr(
            "tools.terminal_tool._resolve_container_task_id",
            lambda _task_id: "default",
        )
        monkeypatch.setattr(
            "tools.file_tools._authoritative_workspace_root",
            lambda task_id: f"/workspace/{task_id}",
        )

        agent._record_file_mutation_result(
            "write_file",
            {"path": "subdir/../config.yaml", "content": "new"},
            json.dumps({"error": "task A failed"}),
            True,
            task_id="remote-task-a",
        )
        agent._record_file_mutation_result(
            "write_file",
            {"path": "config.yaml", "content": "new"},
            json.dumps({"bytes_written": 1, "path": "config.yaml"}),
            False,
            task_id="remote-task-b",
        )

        assert agent._turn_failed_file_mutations

        agent._record_file_mutation_result(
            "write_file",
            {"path": "config.yaml", "content": "new"},
            json.dumps({"bytes_written": 1, "path": "config.yaml"}),
            False,
            task_id="remote-task-a",
        )
        assert agent._turn_failed_file_mutations == {}

    def test_remote_relative_and_absolute_alias_share_authority(self, monkeypatch):
        agent = _bare_agent()
        monkeypatch.setattr(
            "tools.file_tools._terminal_env_type_for_task_strict",
            lambda _task_id: "ssh",
        )
        monkeypatch.setattr(
            "tools.terminal_tool._resolve_container_task_id",
            lambda _task_id: "default",
        )
        monkeypatch.setattr(
            "tools.file_tools._authoritative_workspace_root",
            lambda _task_id: "/workspace/shared",
        )

        agent._record_file_mutation_result(
            "write_file",
            {"path": "config.yaml", "content": "new"},
            json.dumps({"error": "relative write failed"}),
            True,
            task_id="remote-task-a",
        )
        agent._record_file_mutation_result(
            "write_file",
            {"path": "/workspace/shared/config.yaml", "content": "new"},
            json.dumps({"bytes_written": 1, "path": "/workspace/shared/config.yaml"}),
            False,
            task_id="remote-task-b",
        )

        assert agent._turn_failed_file_mutations == {}

    def test_remote_unknown_workspace_does_not_cross_task_ids(self, monkeypatch):
        agent = _bare_agent()
        monkeypatch.setattr(
            "tools.file_tools._terminal_env_type_for_task_strict",
            lambda _task_id: "ssh",
        )
        monkeypatch.setattr(
            "tools.terminal_tool._resolve_container_task_id",
            lambda _task_id: "default",
        )
        monkeypatch.setattr(
            "tools.file_tools._authoritative_workspace_root",
            lambda _task_id: None,
        )

        agent._record_file_mutation_result(
            "write_file",
            {"path": "config.yaml", "content": "new"},
            json.dumps({"error": "task A failed"}),
            True,
            task_id="remote-task-a",
        )
        agent._record_file_mutation_result(
            "write_file",
            {"path": "config.yaml", "content": "new"},
            json.dumps({"bytes_written": 1, "path": "config.yaml"}),
            False,
            task_id="remote-task-b",
        )

        assert agent._turn_failed_file_mutations

        agent._record_file_mutation_result(
            "write_file",
            {"path": "config.yaml", "content": "new"},
            json.dumps({"bytes_written": 1, "path": "config.yaml"}),
            False,
            task_id="remote-task-a",
        )
        assert agent._turn_failed_file_mutations == {}

    def test_unknown_backend_does_not_cross_task_ids(self, monkeypatch):
        agent = _bare_agent()

        def unavailable_backend(_task_id):
            raise RuntimeError("backend lookup unavailable")

        monkeypatch.setattr(
            "tools.file_tools._terminal_env_type_for_task_strict",
            unavailable_backend,
        )
        monkeypatch.setattr(
            "tools.terminal_tool._resolve_container_task_id",
            lambda _task_id: "default",
        )
        monkeypatch.setattr(
            "tools.file_tools._authoritative_workspace_root",
            lambda _task_id: "/workspace/shared",
        )

        agent._record_file_mutation_result(
            "write_file",
            {"path": "config.yaml", "content": "new"},
            json.dumps({"error": "task A failed"}),
            True,
            task_id="task-a",
        )
        agent._record_file_mutation_result(
            "write_file",
            {"path": "config.yaml", "content": "new"},
            json.dumps({"bytes_written": 1, "path": "config.yaml"}),
            False,
            task_id="task-b",
        )

        assert agent._turn_failed_file_mutations

        agent._record_file_mutation_result(
            "write_file",
            {"path": "config.yaml", "content": "new"},
            json.dumps({"bytes_written": 1, "path": "config.yaml"}),
            False,
            task_id="task-a",
        )
        assert agent._turn_failed_file_mutations == {}

    def test_remote_windows_syntax_remains_posix_case_sensitive(self, monkeypatch):
        agent = _bare_agent()
        monkeypatch.setattr(
            "tools.file_tools._terminal_env_type_for_task_strict",
            lambda _task_id: "ssh",
        )
        monkeypatch.setattr(
            "tools.terminal_tool._resolve_container_task_id",
            lambda _task_id: "default",
        )
        monkeypatch.setattr(
            "tools.file_tools._authoritative_workspace_root",
            lambda _task_id: "/workspace/shared",
        )

        agent._record_file_mutation_result(
            "write_file",
            {"path": "C:/Config.yaml", "content": "new"},
            json.dumps({"error": "uppercase path failed"}),
            True,
            task_id="remote-task",
        )
        agent._record_file_mutation_result(
            "write_file",
            {"path": "c:/config.yaml", "content": "new"},
            json.dumps({"bytes_written": 1, "path": "c:/config.yaml"}),
            False,
            task_id="remote-task",
        )

        assert agent._turn_failed_file_mutations

        agent._record_file_mutation_result(
            "write_file",
            {"path": "C:/Config.yaml", "content": "new"},
            json.dumps({"bytes_written": 1, "path": "C:/Config.yaml"}),
            False,
            task_id="remote-task",
        )
        assert agent._turn_failed_file_mutations == {}

    def test_remote_unknown_authority_key_does_not_cross_task_ids(self, monkeypatch):
        agent = _bare_agent()
        monkeypatch.setattr(
            "tools.file_tools._terminal_env_type_for_task_strict",
            lambda _task_id: "ssh",
        )
        monkeypatch.setattr(
            "tools.terminal_tool._resolve_container_task_id",
            lambda _task_id: None,
        )
        monkeypatch.setattr(
            "tools.file_tools._authoritative_workspace_root",
            lambda _task_id: "/workspace/shared",
        )

        agent._record_file_mutation_result(
            "write_file",
            {"path": "config.yaml", "content": "new"},
            json.dumps({"error": "task A failed"}),
            True,
            task_id="remote-task-a",
        )
        agent._record_file_mutation_result(
            "write_file",
            {"path": "config.yaml", "content": "new"},
            json.dumps({"bytes_written": 1, "path": "config.yaml"}),
            False,
            task_id="remote-task-b",
        )

        assert agent._turn_failed_file_mutations

        agent._record_file_mutation_result(
            "write_file",
            {"path": "config.yaml", "content": "new"},
            json.dumps({"bytes_written": 1, "path": "config.yaml"}),
            False,
            task_id="remote-task-a",
        )
        assert agent._turn_failed_file_mutations == {}

    def test_remote_success_cannot_clear_local_failure(
        self,
        monkeypatch,
        tmp_path,
    ):
        agent = _bare_agent()
        target = tmp_path / "config.yaml"
        target.write_text("before\n", encoding="utf-8")
        monkeypatch.setattr(
            "tools.file_tools._terminal_env_type_for_task_strict",
            lambda task_id: "ssh" if task_id == "remote-task" else "local",
        )
        args = {"path": str(target), "content": "after\n"}

        agent._record_file_mutation_result(
            "write_file",
            args,
            json.dumps({"error": "local failure"}),
            True,
            task_id="default",
        )
        agent._record_file_mutation_result(
            "write_file",
            args,
            json.dumps({"bytes_written": 1, "path": str(target)}),
            False,
            task_id="remote-task",
        )

        assert agent._turn_failed_file_mutations

        agent._record_file_mutation_result(
            "write_file",
            args,
            json.dumps({"bytes_written": 1, "path": str(target)}),
            False,
            task_id="default",
        )
        assert agent._turn_failed_file_mutations == {}

    def test_remote_success_cannot_clear_another_remote_task(self, monkeypatch):
        agent = _bare_agent()
        monkeypatch.setattr(
            "tools.file_tools._terminal_env_type_for_task_strict",
            lambda _task_id: "ssh",
        )
        monkeypatch.setattr(
            "tools.terminal_tool._resolve_container_task_id",
            lambda task_id: task_id,
        )
        args = {"path": "subdir/../config.yaml", "content": "new"}

        agent._record_file_mutation_result(
            "write_file",
            args,
            json.dumps({"error": "task A failed"}),
            True,
            task_id="remote-task-a",
        )
        agent._record_file_mutation_result(
            "write_file",
            {"path": "config.yaml", "content": "new"},
            json.dumps({"bytes_written": 1, "path": "config.yaml"}),
            False,
            task_id="remote-task-b",
        )

        assert agent._turn_failed_file_mutations

        agent._record_file_mutation_result(
            "write_file",
            {"path": "config.yaml", "content": "new"},
            json.dumps({"bytes_written": 1, "path": "config.yaml"}),
            False,
            task_id="remote-task-a",
        )
        assert agent._turn_failed_file_mutations == {}

    def test_remote_lexical_identity_is_collision_safe(self, monkeypatch):
        agent = _bare_agent()
        monkeypatch.setattr(
            "tools.file_tools._terminal_env_type_for_task_strict",
            lambda _task_id: "ssh",
        )
        monkeypatch.setattr(
            "tools.terminal_tool._resolve_container_task_id",
            lambda task_id: task_id,
        )

        agent._record_file_mutation_result(
            "write_file",
            {"path": "config.yaml", "content": "new"},
            json.dumps({"error": "task A failed"}),
            True,
            task_id="remote:a",
        )
        agent._record_file_mutation_result(
            "write_file",
            {"path": "a:config.yaml", "content": "new"},
            json.dumps({"bytes_written": 1, "path": "a:config.yaml"}),
            False,
            task_id="remote",
        )

        assert agent._turn_failed_file_mutations

    def test_unobservable_local_alias_clears_across_tasks_sharing_workspace(
        self,
        monkeypatch,
    ):
        agent = _bare_agent()
        monkeypatch.setattr(
            "tools.file_tools._terminal_env_type_for_task_strict",
            lambda _task_id: "local",
        )
        monkeypatch.setattr(
            agent,
            "_resolved_file_mutation_target_path",
            lambda _path, _task_id: None,
        )
        monkeypatch.setattr(
            "tools.file_tools._authoritative_workspace_root",
            lambda _task_id: "C:/workspace/shared",
        )

        agent._record_file_mutation_result(
            "write_file",
            {"path": "subdir/../config.yaml", "content": "new"},
            json.dumps({"error": "task A failed"}),
            True,
            task_id="local-task-a",
        )
        agent._record_file_mutation_result(
            "write_file",
            {"path": "config.yaml", "content": "new"},
            json.dumps({"bytes_written": 1, "path": "config.yaml"}),
            False,
            task_id="local-task-b",
        )

        assert agent._turn_failed_file_mutations == {}

    def test_unobservable_local_success_cannot_clear_another_workspace(
        self,
        monkeypatch,
    ):
        agent = _bare_agent()
        monkeypatch.setattr(
            "tools.file_tools._terminal_env_type_for_task_strict",
            lambda _task_id: "local",
        )
        monkeypatch.setattr(
            agent,
            "_resolved_file_mutation_target_path",
            lambda _path, _task_id: None,
        )
        monkeypatch.setattr(
            "tools.file_tools._authoritative_workspace_root",
            lambda task_id: f"C:/workspace/{task_id}",
        )
        args = {"path": "subdir/../config.yaml", "content": "new"}

        agent._record_file_mutation_result(
            "write_file",
            args,
            json.dumps({"error": "task A failed"}),
            True,
            task_id="local-task-a",
        )
        agent._record_file_mutation_result(
            "write_file",
            {"path": "config.yaml", "content": "new"},
            json.dumps({"bytes_written": 1, "path": "config.yaml"}),
            False,
            task_id="local-task-b",
        )

        assert agent._turn_failed_file_mutations

        agent._record_file_mutation_result(
            "write_file",
            {"path": "config.yaml", "content": "new"},
            json.dumps({"bytes_written": 1, "path": "config.yaml"}),
            False,
            task_id="local-task-a",
        )
        assert agent._turn_failed_file_mutations == {}

    @pytest.mark.skipif(os.name != "nt", reason="Windows absolute-path semantics")
    def test_unobservable_absolute_local_alias_clears_across_workspaces(
        self,
        monkeypatch,
    ):
        agent = _bare_agent()
        monkeypatch.setattr(
            "tools.file_tools._terminal_env_type_for_task_strict",
            lambda _task_id: "local",
        )
        monkeypatch.setattr(
            agent,
            "_resolved_file_mutation_target_path",
            lambda _path, _task_id: None,
        )
        monkeypatch.setattr(
            "tools.file_tools._authoritative_workspace_root",
            lambda task_id: f"C:/workspace/{task_id}",
        )

        agent._record_file_mutation_result(
            "write_file",
            {"path": "C:/shared/config.yaml", "content": "new"},
            json.dumps({"error": "task A failed"}),
            True,
            task_id="local-task-a",
        )
        agent._record_file_mutation_result(
            "write_file",
            {"path": r"c:\shared\.\config.yaml", "content": "new"},
            json.dumps({"bytes_written": 1, "path": "config.yaml"}),
            False,
            task_id="local-task-b",
        )

        assert agent._turn_failed_file_mutations == {}

    def test_alias_resolution_and_hashing_are_bounded(self):
        agent = _bare_agent()
        resolve_calls = []
        snapshot_calls = []
        canonical = "/tmp/project/config.yaml"
        unique = "/tmp/project/unique.yaml"

        def resolve(path, _task_id):
            resolve_calls.append(path)
            return unique if path == unique else canonical

        agent._resolved_file_mutation_target_path = resolve
        agent._snapshot_resolved_file_mutation_target = (
            lambda path: snapshot_calls.append(path) or {
                "path": path,
                "signature": ("present", 1, b"digest"),
            }
        )
        marker = "*** "
        body = marker + "Begin Patch\n"
        for index in range(99):
            body += (
                marker
                + f"Update File: /tmp/project/alias-{index}/../config.yaml\n"
                + "@@ @@\n-a\n+b\n"
            )
        body += marker + f"Update File: {unique}\n@@ @@\n-a\n+b\n"
        body += marker + "End Patch\n"

        snapshots = agent._snapshot_failed_file_mutation_targets(
            "patch",
            {"mode": "patch", "patch": body},
            json.dumps({"error": "parse failure"}),
            is_error=True,
        )

        assert len(resolve_calls) == 2
        assert snapshot_calls == [canonical, unique]
        assert len(snapshots) == 100

    @staticmethod
    def _many_target_patch_body(count: int) -> str:
        marker = "*** "
        parts = [marker + "Begin Patch\n"]
        for index in range(count):
            parts.append(
                marker
                + f"Update File: /tmp/file-{index}.md\n@@ @@\n-a\n+b\n"
            )
        parts.append(marker + "End Patch\n")
        return "".join(parts)

    def test_oversized_failure_has_recoverable_aggregate_warning(self):
        body = self._many_target_patch_body(101)
        args = {"mode": "patch", "patch": body}
        agent = _bare_agent()
        agent._snapshot_failed_file_mutation_targets = lambda *_args, **_kwargs: {}

        agent._record_file_mutation_result(
            "patch",
            args,
            json.dumps({"error": "batch failed"}),
            is_error=True,
            task_id="task-a",
        )

        overflow = [
            info
            for info in agent._turn_failed_file_mutations.values()
            if info.get("_mutation_failure_overflow")
        ]
        assert len(agent._turn_failed_file_mutations) == 100
        assert len(overflow) == 1
        assert overflow[0]["_overflow_count"] == 2

        agent._record_file_mutation_result(
            "patch",
            args,
            json.dumps({"success": True}),
            is_error=False,
            task_id="task-a",
        )

        assert agent._turn_failed_file_mutations == {}

    def test_oversized_recovery_uses_shared_authority_scope(self, monkeypatch):
        body = self._many_target_patch_body(101)
        args = {"mode": "patch", "patch": body}
        agent = _bare_agent()
        agent._snapshot_failed_file_mutation_targets = lambda *_args, **_kwargs: {}
        monkeypatch.setattr(
            "tools.file_tools._terminal_env_type_for_task_strict",
            lambda _task_id: "ssh",
        )
        monkeypatch.setattr(
            "tools.terminal_tool._resolve_container_task_id",
            lambda _task_id: "shared-authority",
        )
        monkeypatch.setattr(
            "tools.file_tools._authoritative_workspace_root",
            lambda _task_id: "/workspace",
        )

        agent._record_file_mutation_result(
            "patch",
            args,
            json.dumps({"error": "batch failed"}),
            is_error=True,
            task_id="task-a",
        )
        agent._record_file_mutation_result(
            "patch",
            args,
            json.dumps({"success": True}),
            is_error=False,
            task_id="task-b",
        )

        assert agent._turn_failed_file_mutations == {}

    def test_snapshot_budget_caps_unique_v4a_targets(self):
        body = self._many_target_patch_body(12)
        agent = _bare_agent()
        direct_calls = []
        agent._resolved_file_mutation_target_path = lambda path, _task_id: path
        agent._snapshot_resolved_file_mutation_target = (
            lambda path: direct_calls.append(path) or None
        )

        agent._record_file_mutation_result(
            "patch",
            {"mode": "patch", "patch": body},
            json.dumps({"error": "parse failure"}),
            is_error=True,
        )

        assert len(agent._turn_failed_file_mutations) == 12
        assert len(direct_calls) == 10

        worker_agent = _bare_agent()
        worker_calls = []
        worker_agent._resolved_file_mutation_target_path = (
            lambda path, _task_id: path
        )
        worker_agent._snapshot_resolved_file_mutation_target = (
            lambda path: worker_calls.append(path) or None
        )
        snapshots = worker_agent._snapshot_failed_file_mutation_targets(
            "patch",
            {"mode": "patch", "patch": body},
            json.dumps({"error": "parse failure"}),
            is_error=True,
        )

        assert len(snapshots) == 12
        assert len(worker_calls) == 10
        assert sum(snapshot is None for snapshot in snapshots.values()) == 12

    def test_snapshot_budget_is_shared_across_failed_calls(self):
        agent = _bare_agent()
        snapshot_calls = []
        agent._resolved_file_mutation_target_path = lambda path, _task_id: path
        agent._snapshot_resolved_file_mutation_target = (
            lambda path: snapshot_calls.append(path) or {
                "path": path,
                "signature": ("missing",),
            }
        )

        for start in (0, 6):
            marker = "*** "
            body = marker + "Begin Patch\n"
            for index in range(start, start + 6):
                body += (
                    marker
                    + f"Update File: /tmp/budget-{index}.md\n@@ @@\n-a\n+b\n"
                )
            body += marker + "End Patch\n"
            agent._snapshot_failed_file_mutation_targets(
                "patch",
                {"mode": "patch", "patch": body},
                json.dumps({"error": "parse failure"}),
                is_error=True,
            )

        assert len(snapshot_calls) == 10

    def test_turn_budget_caps_identity_resolution_across_failed_records(
        self,
        monkeypatch,
    ):
        agent = _bare_agent()
        resolve_calls = []
        monkeypatch.setattr(
            AIAgent,
            "_resolved_file_mutation_target_path",
            staticmethod(
                lambda path, _task_id="default": resolve_calls.append(path) or None
            ),
        )

        for index in range(12):
            path = f"offline-{index}.txt"
            agent._record_file_mutation_result(
                "write_file",
                {"path": path, "content": "new"},
                json.dumps({"error": "failed"}),
                is_error=True,
                failure_snapshots={path: None},
            )

        assert len(resolve_calls) <= 10
        assert len(agent._turn_failed_file_mutations) == 12

    def test_success_without_failures_preserves_observation_budget(
        self,
        monkeypatch,
    ):
        agent = _bare_agent()
        resolve_calls = []
        monkeypatch.setattr(
            AIAgent,
            "_resolved_file_mutation_target_path",
            staticmethod(
                lambda path, _task_id="default": resolve_calls.append(path) or path
            ),
        )

        agent._record_file_mutation_result(
            "write_file",
            {"path": "already-ok.txt", "content": "new"},
            json.dumps({"bytes_written": 1, "path": "already-ok.txt"}),
            is_error=False,
        )

        assert resolve_calls == []
        budget = getattr(agent, "_turn_file_mutation_snapshot_budget", None)
        assert budget is None or budget["remaining"] == 10

    def test_success_clears_local_failure_after_budget_is_exhausted(self, tmp_path):
        agent = _bare_agent()
        target = tmp_path / "recovered.txt"
        target.write_text("before\n", encoding="utf-8")

        agent._record_file_mutation_result(
            "write_file",
            {"path": str(target), "content": "after\n"},
            json.dumps({"error": "failed"}),
            is_error=True,
        )
        assert agent._claim_file_mutation_snapshot_slots(9) == 9

        agent._record_file_mutation_result(
            "write_file",
            {"path": str(target), "content": "after\n"},
            json.dumps({"bytes_written": 1, "path": str(target)}),
            is_error=False,
        )

        assert agent._turn_failed_file_mutations == {}

    def test_absolute_success_clears_relative_failure_after_budget_is_exhausted(
        self,
        monkeypatch,
        tmp_path,
    ):
        agent = _bare_agent()
        target = tmp_path / "recovered.txt"
        target.write_text("before\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)

        agent._record_file_mutation_result(
            "write_file",
            {"path": "recovered.txt", "content": "after\n"},
            json.dumps({"error": "failed"}),
            is_error=True,
            failure_snapshots={"recovered.txt": None},
        )
        assert agent._claim_file_mutation_snapshot_slots(10) == 10

        agent._record_file_mutation_result(
            "write_file",
            {"path": str(target), "content": "after\n"},
            json.dumps({"bytes_written": 1, "path": str(target)}),
            is_error=False,
        )

        assert agent._turn_failed_file_mutations == {}

    def test_snapshot_budget_claim_is_thread_safe(self):
        agent = _bare_agent()

        with ThreadPoolExecutor(max_workers=20) as pool:
            grants = list(pool.map(
                lambda _index: agent._claim_file_mutation_snapshot_slots(1),
                range(20),
            ))

        assert sum(grants) == 10
        assert grants.count(1) == 10
        assert grants.count(0) == 10




# ---------------------------------------------------------------------------
# _format_file_mutation_failure_footer
# ---------------------------------------------------------------------------


class TestFormatFooter:
    def test_empty_returns_empty_string(self):
        assert AIAgent._format_file_mutation_failure_footer({}) == ""

    def test_single_failure(self):
        out = AIAgent._format_file_mutation_failure_footer(
            {"/tmp/a.md": {"tool": "patch", "error_preview": "Could not find old_string"}},
        )
        assert "unresolved failed file-tool mutations for 1 file(s)" in out
        assert "/tmp/a.md" in out
        assert "Could not find old_string" in out
        assert "git status" in out  # user-actionable hint

    def test_truncation_at_10_entries(self):
        failed = {
            f"/tmp/f{i}.md": {"tool": "patch", "error_preview": "err"}
            for i in range(15)
        }
        out = AIAgent._format_file_mutation_failure_footer(failed)
        assert "unresolved failed file-tool mutations for 15 file(s)" in out
        assert "… and 5 more" in out
        # Ten file bullets + header + "and X more" line
        lines = out.split("\n")
        bullet_lines = [ln for ln in lines if ln.lstrip().startswith("•")]
        assert len(bullet_lines) == 11  # 10 shown + 1 summary

    def test_alias_recovery_reads_resolved_target_once(self, monkeypatch):
        calls = []

        def signature(path):
            calls.append(path)
            return ("present", 1, b"after")

        monkeypatch.setattr(
            AIAgent,
            "_file_mutation_disk_signature",
            staticmethod(signature),
        )
        snapshot = {
            "path": "/tmp/project/config.yaml",
            "signature": ("present", 1, b"before"),
        }
        failed = {
            "/tmp/project/config.yaml": {
                "tool": "patch",
                "error_preview": "failed",
                "disk_snapshot": snapshot,
            },
            "/tmp/project/./config.yaml": {
                "tool": "patch",
                "error_preview": "failed",
                "disk_snapshot": snapshot,
            },
        }

        assert AIAgent._format_file_mutation_failure_footer(failed) == ""
        assert calls == ["/tmp/project/config.yaml"]

    def test_paths_are_backtick_wrapped(self):
        """Footer paths must be inline-code wrapped so the gateway's bare-path
        media extractor can't auto-attach them (#35584 defense-in-depth)."""
        out = AIAgent._format_file_mutation_failure_footer(
            {"/home/u/.hermes/config.yaml": {
                "tool": "patch",
                "error_preview": (
                    "Write denied: '/home/u/.hermes/config.yaml' is a "
                    "protected system/credential file."
                ),
            }},
        )
        # Path still human-readable.
        assert "/home/u/.hermes/config.yaml" in out
        # Bullet path is backticked.
        assert "`/home/u/.hermes/config.yaml`" in out
        # The path echoed inside the preview is ALSO backticked (the real
        # file_operations.py denial message embeds it in single quotes, which
        # do NOT block the gateway extractor's regex).
        assert "'`/home/u/.hermes/config.yaml`'" in out
        # No double-backticking anywhere.
        assert "``" not in out

    def test_footer_path_not_extracted_by_gateway(self):
        """End-to-end: the gateway's extract_local_files must NOT pull a
        config.yaml path out of the rendered footer (#35584)."""
        import os
        import tempfile
        from gateway.platforms.base import BasePlatformAdapter

        tmp = tempfile.mkdtemp(prefix="hermes_footer_")
        try:
            cfg = os.path.join(tmp, "config.yaml")
            with open(cfg, "w") as fh:
                fh.write("openrouter_api_key: sk-LEAK\n")
            footer = AIAgent._format_file_mutation_failure_footer(
                {cfg: {
                    "tool": "patch",
                    "error_preview": (
                        f"Write denied: '{cfg}' is a protected "
                        "system/credential file."
                    ),
                }},
            )
            response = "I updated your config.\n\n" + footer
            paths, _ = BasePlatformAdapter.extract_local_files(response)
            assert paths == [], f"footer leaked deliverable path(s): {paths}"
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_footer_backtick_in_model_path_cannot_escape_inline_code(self, tmp_path):
        from gateway.platforms.base import BasePlatformAdapter

        target = tmp_path / "victim.md"
        target.write_text("private fixture\n", encoding="utf-8")
        malicious_path = f"bad`{target}"
        footer = AIAgent._format_file_mutation_failure_footer(
            {malicious_path: {"tool": "patch", "error_preview": "failed"}},
        )

        paths, _ = BasePlatformAdapter.extract_local_files(footer)

        assert paths == []

    @pytest.mark.parametrize("field", ["path", "display_path", "tool", "preview"])
    def test_footer_model_fields_cannot_emit_media_directives(self, tmp_path, field):
        from gateway.platforms.base import BasePlatformAdapter

        target = tmp_path / "private.txt"
        target.write_text("private fixture\n", encoding="utf-8")
        directive = f"MEDIA:{target}"
        path = directive if field == "path" else "ordinary-path"
        info = {"tool": "patch", "error_preview": "failed"}
        if field == "display_path":
            info["_display_path"] = directive
        elif field == "tool":
            info["tool"] = directive
        elif field == "preview":
            info["error_preview"] = directive

        footer = AIAgent._format_file_mutation_failure_footer({path: info})
        media, _ = BasePlatformAdapter.extract_media(footer)
        local_paths, _ = BasePlatformAdapter.extract_local_files(footer)

        assert media == []
        assert local_paths == []


# ---------------------------------------------------------------------------
# _file_mutation_verifier_enabled — env + config precedence
# ---------------------------------------------------------------------------


class TestVerifierEnabled:
    def test_default_is_enabled(self, monkeypatch):
        monkeypatch.delenv("HERMES_FILE_MUTATION_VERIFIER", raising=False)
        agent = _bare_agent()
        # With no env and no config present, safe default is True.
        # load_config may surface a user config.yaml in some envs — stub it.
        import hermes_cli.config as _cfg_mod
        monkeypatch.setattr(_cfg_mod, "load_config", lambda: {})
        assert agent._file_mutation_verifier_enabled() is True

    @pytest.mark.parametrize("value", ["0", "false", "FALSE", "no", "off"])
    def test_env_disables(self, monkeypatch, value):
        monkeypatch.setenv("HERMES_FILE_MUTATION_VERIFIER", value)
        agent = _bare_agent()
        assert agent._file_mutation_verifier_enabled() is False




# ---------------------------------------------------------------------------
# Module-level invariants
# ---------------------------------------------------------------------------


def test_file_mutating_tools_set_shape():
    """write_file + patch are the only tools the verifier tracks.

    Guard rail: if someone adds a third file-mutating tool (e.g. a new
    ``append_file``), they should also audit whether the verifier should
    track it.  This test fails loudly on unilateral additions.
    """
    assert _FILE_MUTATING_TOOLS == frozenset({"write_file", "patch"})
