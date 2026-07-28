"""Behavioral tests for the content-transition file-mutation verifier redesign."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from agent.file_mutation_verifier import (
    ContentFingerprint,
    DispatchTriState,
    TurnFileMutationVerifier,
    _path_allowed_for_observation,
    format_failure_footer,
    sync_legacy_failed_state,
)
from run_agent import AIAgent, _extract_file_mutation_targets


def _bare_agent() -> AIAgent:
    from agent.file_mutation_verifier import TurnFileMutationVerifier

    agent = object.__new__(AIAgent)
    agent._turn_failed_file_mutations = {}
    agent._turn_file_mutation_paths = set()
    agent._file_mutation_verifier = TurnFileMutationVerifier()
    agent._file_mutation_verifier.reset_turn(1)
    return agent


class TestContentTransitionSuppressesFooter:
    def test_failed_patch_then_external_edit_clears_footer(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        target = tmp_path / "config.yaml"
        target.write_text("before: true\n", encoding="utf-8")

        agent = _bare_agent()
        fail = json.dumps({"success": False, "error": "Write denied (simulated)"})
        agent._record_file_mutation_result(
            "patch",
            {"mode": "replace", "path": "config.yaml", "old_string": "x", "new_string": "y"},
            fail,
            is_error=True,
            raw_result=fail,
            dispatch=DispatchTriState.DISPATCHED.value,
            effective_task_id="default",
        )
        assert agent._turn_failed_file_mutations

        target.write_text("after: true\n", encoding="utf-8")
        from agent.file_mutation_verifier import sync_legacy_failed_state

        sync_legacy_failed_state(agent)
        assert agent._turn_failed_file_mutations == {}

    def test_unchanged_file_keeps_footer(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        target = tmp_path / "stale.py"
        target.write_text("same\n", encoding="utf-8")

        agent = _bare_agent()
        fail = json.dumps({"error": "Could not find old_string"})
        agent._record_file_mutation_result(
            "patch",
            {"mode": "replace", "path": "stale.py", "old_string": "nope", "new_string": "y"},
            fail,
            is_error=True,
            raw_result=fail,
            dispatch=DispatchTriState.DISPATCHED.value,
        )
        from agent.file_mutation_verifier import sync_legacy_failed_state

        sync_legacy_failed_state(agent)
        assert any(k.endswith("stale.py") for k in agent._turn_failed_file_mutations)


class TestDispatchTriState:
    def test_not_dispatched_creates_no_ledger_io(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        agent = _bare_agent()
        agent._record_file_mutation_result(
            "write_file",
            {"path": "new.txt", "content": "x"},
            json.dumps({"bytes_written": 1}),
            is_error=False,
            dispatch=DispatchTriState.NOT_DISPATCHED.value,
            blocked=True,
        )
        assert agent._turn_failed_file_mutations == {}

    def test_middleware_short_circuit_does_not_clear_prior_failure(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "a.txt").write_text("x\n", encoding="utf-8")
        agent = _bare_agent()
        fail = json.dumps({"error": "first"})
        agent._record_file_mutation_result(
            "patch",
            {"mode": "replace", "path": "a.txt", "old_string": "x", "new_string": "y"},
            fail,
            is_error=True,
            raw_result=fail,
            dispatch=DispatchTriState.DISPATCHED.value,
        )
        agent._record_file_mutation_result(
            "write_file",
            {"path": "a.txt", "content": "landed"},
            json.dumps({"bytes_written": 6}),
            is_error=False,
            dispatch=DispatchTriState.NOT_DISPATCHED.value,
        )
        from agent.file_mutation_verifier import sync_legacy_failed_state

        sync_legacy_failed_state(agent)
        assert any(k.endswith("a.txt") for k in agent._turn_failed_file_mutations)


class TestV4aParserParity:
    def test_crlf_and_compact_headers_use_parser(self):
        body = (
            "*** Begin Patch\r\n"
            "***Update File: a.py\r\n"
            "@@ @@\r\n"
            "-a\r\n"
            "+b\r\n"
            "*** End Patch\r\n"
        )
        assert _extract_file_mutation_targets("patch", {"mode": "patch", "patch": body}) == ["a.py"]

    def test_invalid_patch_yields_no_targets(self):
        body = "*** Update File: outside\n*** Begin Patch\n*** End Patch\n"
        assert _extract_file_mutation_targets("patch", {"mode": "patch", "patch": body}) == []

    def test_dispatched_failure_without_targets_fails_closed(self):
        from agent.file_mutation_verifier import _UNKNOWN_MUTATION_TARGET

        verifier = TurnFileMutationVerifier(use_subprocess_fingerprint=False)
        verifier.reset_turn(1)
        body = "*** Update File: outside\n*** Begin Patch\n*** End Patch\n"
        fail = json.dumps({"error": "Could not apply patch"})
        verifier.record_tool_outcome(
            tool_name="patch",
            effective_args={"mode": "patch", "patch": body},
            effective_task_id="default",
            raw_result=fail,
            dispatch=DispatchTriState.DISPATCHED,
            model_is_error=True,
            turn_generation=1,
        )
        failed = verifier.finalize_failed_dict()
        assert _UNKNOWN_MUTATION_TARGET in failed
        assert "Could not apply patch" in failed[_UNKNOWN_MUTATION_TARGET]["error_preview"]


class TestPathSafety:
    @pytest.mark.skipif(__import__("sys").platform != "win32", reason="DOS device paths")
    def test_dos_device_rejected(self):
        assert not _path_allowed_for_observation(r"\\.\CON")

    def test_unc_rejected(self):
        assert not _path_allowed_for_observation(r"\\server\share\file.txt")

    def test_safety_check_exception_fails_closed(self, monkeypatch):
        def _raise(_path):
            raise RuntimeError("safety policy unavailable")

        monkeypatch.setattr("agent.file_safety.get_read_block_error", _raise)
        assert not _path_allowed_for_observation("ordinary.txt")


class TestFooterSanitization:
    def test_media_injection_neutralized(self):
        failed = {
            "/tmp/x.md": {
                "tool": "patch",
                "error_preview": "MEDIA: /etc/passwd\nfailed",
            }
        }
        out = format_failure_footer(failed, format_paths=lambda s: s)
        assert "MEDIA:" not in out
        assert "[filtered]" in out

    def test_path_injection_is_neutralized(self):
        failed = {
            "safe.txt`\nMEDIA: /tmp/private.png\n\x1b[31m": {
                "tool": "patch",
                "error_preview": "failed",
            }
        }
        out = format_failure_footer(failed, format_paths=lambda s: s)
        assert "MEDIA:" not in out
        assert "\x1b" not in out
        assert "[filtered]" in out

    def test_inline_media_directive_cannot_attach_an_existing_file(self, tmp_path):
        from gateway.platforms.base import BasePlatformAdapter

        target = tmp_path / "private.png"
        target.write_bytes(b"not-an-image")
        failed = {
            str(tmp_path / "failed.txt"): {
                "tool": "write_file",
                "error_preview": f"write failed MEDIA:{target}",
            }
        }

        out = AIAgent._format_file_mutation_failure_footer(failed)
        media, _ = BasePlatformAdapter.extract_media(out)

        assert media == []
        assert "MEDIA:" not in out


class TestMetadataOnlyChange:
    def test_mtime_only_does_not_suppress_footer(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        target = tmp_path / "meta.py"
        target.write_text("content\n", encoding="utf-8")
        agent = _bare_agent()
        agent._file_mutation_verifier.prepare_mutation_dispatch(
            tool_name="patch",
            effective_args={
                "mode": "replace",
                "path": "meta.py",
                "old_string": "x",
                "new_string": "y",
            },
            effective_task_id="default",
            turn_generation=1,
        )
        fail = json.dumps({"error": "failed"})
        agent._record_file_mutation_result(
            "patch",
            {"mode": "replace", "path": "meta.py", "old_string": "x", "new_string": "y"},
            fail,
            is_error=True,
            raw_result=fail,
            dispatch=DispatchTriState.DISPATCHED.value,
            turn_generation=1,
        )
        import os

        os.utime(target, None)
        from agent.file_mutation_verifier import sync_legacy_failed_state

        sync_legacy_failed_state(agent)
        assert any(k.endswith("meta.py") for k in agent._turn_failed_file_mutations)


class TestPathAliasReconciliation:
    def test_relative_and_absolute_same_file_clears(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        target = tmp_path / "alias.py"
        target.write_text("start\n", encoding="utf-8")
        agent = _bare_agent()
        fail = json.dumps({"error": "nope"})
        agent._record_file_mutation_result(
            "patch",
            {"mode": "replace", "path": "alias.py", "old_string": "x", "new_string": "y"},
            fail,
            is_error=True,
            raw_result=fail,
            dispatch=DispatchTriState.DISPATCHED.value,
        )
        target.write_text("end\n", encoding="utf-8")
        agent._file_mutation_verifier.reconcile_content_transitions(task_id="default")
        from agent.file_mutation_verifier import sync_legacy_failed_state

        sync_legacy_failed_state(agent)
        assert agent._turn_failed_file_mutations == {}

    def test_successful_absolute_creation_clears_failed_relative_alias(
        self, tmp_path, monkeypatch,
    ):
        monkeypatch.chdir(tmp_path)
        target = tmp_path / "created.py"
        verifier = TurnFileMutationVerifier(use_subprocess_fingerprint=False)
        verifier.reset_turn(1)

        verifier.record_tool_outcome(
            tool_name="write_file",
            effective_args={"path": "created.py", "content": "new\n"},
            effective_task_id="default",
            raw_result=json.dumps({"error": "first attempt failed"}),
            dispatch=DispatchTriState.DISPATCHED,
            model_is_error=True,
            turn_generation=1,
        )
        assert "created.py" in verifier.finalize_failed_dict()

        target.write_text("new\n", encoding="utf-8")
        verifier.record_tool_outcome(
            tool_name="write_file",
            effective_args={"path": str(target), "content": "new\n"},
            effective_task_id="default",
            raw_result=json.dumps(
                {"success": True, "path": str(target), "bytes_written": 4}
            ),
            dispatch=DispatchTriState.DISPATCHED,
            model_is_error=False,
            turn_generation=1,
        )

        assert verifier.finalize_failed_dict() == {}


class TestTurnGenerationBudget:
    def test_stale_generation_does_not_record(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        agent = _bare_agent()
        agent._file_mutation_verifier.reset_turn(2)
        fail = json.dumps({"error": "late"})
        agent._record_file_mutation_result(
            "write_file",
            {"path": "z.txt", "content": "a"},
            fail,
            is_error=True,
            raw_result=fail,
            dispatch=DispatchTriState.DISPATCHED.value,
            turn_generation=1,
        )
        assert agent._turn_failed_file_mutations == {}

    def test_reset_during_snapshot_discards_old_generation_result(
        self, tmp_path, monkeypatch,
    ):
        target = tmp_path / "race.txt"
        target.write_text("old\n", encoding="utf-8")
        verifier = TurnFileMutationVerifier(use_subprocess_fingerprint=False)
        verifier.reset_turn(1)
        started = threading.Event()
        release = threading.Event()
        observed = {}

        def _slow_fingerprint(*_args, **_kwargs):
            started.set()
            assert release.wait(timeout=5)
            return (
                ContentFingerprint(
                    size=4,
                    digest=b"old-generation",
                    mtime_ns=1,
                    inode=1,
                ),
                4,
            )

        monkeypatch.setattr(
            "agent.file_mutation_verifier._stable_local_fingerprint",
            _slow_fingerprint,
        )

        worker = threading.Thread(
            target=lambda: observed.setdefault(
                "result",
                verifier._capture_baseline(
                    str(target),
                    "default",
                    turn_generation=1,
                ),
            )
        )
        worker.start()
        assert started.wait(timeout=5)
        verifier.reset_turn(2)
        release.set()
        worker.join(timeout=5)

        assert not worker.is_alive()
        assert observed["result"] is None
        assert verifier._budget.snapshot_attempts == 0
        assert verifier._budget.snapshot_bytes == 0


class TestPreDispatchBaseline:
    def test_unchanged_file_after_prepare_keeps_failure(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        target = tmp_path / "partial.py"
        target.write_text("baseline\n", encoding="utf-8")
        verifier = TurnFileMutationVerifier(use_subprocess_fingerprint=False)
        verifier.reset_turn(1)
        verifier.prepare_mutation_dispatch(
            tool_name="write_file",
            effective_args={"path": "partial.py", "content": "changed\n"},
            effective_task_id="default",
            turn_generation=1,
        )
        verifier.record_tool_outcome(
            tool_name="write_file",
            effective_args={"path": "partial.py", "content": "changed\n"},
            effective_task_id="default",
            raw_result=json.dumps({"error": "disk full"}),
            dispatch=DispatchTriState.DISPATCHED,
            model_is_error=True,
            turn_generation=1,
        )
        assert "partial.py" in verifier.finalize_failed_dict()

    def test_explicit_partial_write_failure_requires_later_transition(
        self, tmp_path, monkeypatch,
    ):
        monkeypatch.chdir(tmp_path)
        target = tmp_path / "partial.py"
        target.write_text("baseline\n", encoding="utf-8")
        verifier = TurnFileMutationVerifier(use_subprocess_fingerprint=False)
        verifier.reset_turn(1)
        verifier.prepare_mutation_dispatch(
            tool_name="write_file",
            effective_args={"path": "partial.py", "content": "changed\n"},
            effective_task_id="default",
            turn_generation=1,
        )
        target.write_text("mutated-on-disk\n", encoding="utf-8")
        verifier.record_tool_outcome(
            tool_name="write_file",
            effective_args={"path": "partial.py", "content": "changed\n"},
            effective_task_id="default",
            raw_result=json.dumps({"error": "disk full"}),
            dispatch=DispatchTriState.DISPATCHED,
            model_is_error=True,
            turn_generation=1,
        )
        assert "partial.py" in verifier.finalize_failed_dict()

        target.write_text("later-recovery\n", encoding="utf-8")
        assert verifier.finalize_failed_dict() == {}

    def test_timeout_uses_pre_dispatch_baseline_for_late_effect(
        self, tmp_path, monkeypatch,
    ):
        monkeypatch.chdir(tmp_path)
        target = tmp_path / "timeout.py"
        target.write_text("before\n", encoding="utf-8")
        verifier = TurnFileMutationVerifier(use_subprocess_fingerprint=False)
        verifier.reset_turn(1)
        args = {"path": "timeout.py", "content": "after\n"}

        verifier.prepare_mutation_dispatch(
            tool_name="write_file",
            effective_args=args,
            effective_task_id="default",
            turn_generation=1,
        )
        target.write_text("after\n", encoding="utf-8")
        verifier.record_tool_outcome(
            tool_name="write_file",
            effective_args=args,
            effective_task_id="default",
            raw_result=None,
            dispatch=DispatchTriState.DISPATCHED_NO_RESULT,
            model_is_error=True,
            turn_generation=1,
        )

        assert verifier.finalize_failed_dict() == {}


class TestRecoveredThenFailedAgain:
    def test_later_failure_after_transition(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        p = tmp_path / "flip.py"
        p.write_text("v1\n", encoding="utf-8")
        agent = _bare_agent()
        fail1 = json.dumps({"error": "first"})
        agent._record_file_mutation_result(
            "patch",
            {"mode": "replace", "path": "flip.py", "old_string": "v1", "new_string": "v2"},
            fail1,
            is_error=True,
            raw_result=fail1,
            dispatch=DispatchTriState.DISPATCHED.value,
        )
        p.write_text("v2\n", encoding="utf-8")
        from agent.file_mutation_verifier import sync_legacy_failed_state

        sync_legacy_failed_state(agent)
        assert agent._turn_failed_file_mutations == {}

        fail2 = json.dumps({"error": "second failure"})
        agent._record_file_mutation_result(
            "patch",
            {"mode": "replace", "path": "flip.py", "old_string": "v9", "new_string": "v3"},
            fail2,
            is_error=True,
            raw_result=fail2,
            dispatch=DispatchTriState.DISPATCHED.value,
        )
        sync_legacy_failed_state(agent)
        assert any(k.endswith("flip.py") for k in agent._turn_failed_file_mutations)
        key = next(k for k in agent._turn_failed_file_mutations if k.endswith("flip.py"))
        assert "second failure" in agent._turn_failed_file_mutations[key]["error_preview"]

    def test_repeated_failure_refreshes_post_result_baseline(
        self, tmp_path, monkeypatch,
    ):
        monkeypatch.chdir(tmp_path)
        target = tmp_path / "retry.py"
        target.write_text("v1\n", encoding="utf-8")
        verifier = TurnFileMutationVerifier(use_subprocess_fingerprint=False)
        verifier.reset_turn(1)
        args = {"path": "retry.py", "content": "requested\n"}

        verifier.prepare_mutation_dispatch(
            tool_name="write_file",
            effective_args=args,
            effective_task_id="default",
            turn_generation=1,
        )
        verifier.record_tool_outcome(
            tool_name="write_file",
            effective_args=args,
            effective_task_id="default",
            raw_result=json.dumps({"error": "first"}),
            dispatch=DispatchTriState.DISPATCHED,
            model_is_error=True,
            turn_generation=1,
        )

        target.write_text("v2\n", encoding="utf-8")
        verifier.prepare_mutation_dispatch(
            tool_name="write_file",
            effective_args=args,
            effective_task_id="default",
            turn_generation=1,
        )
        verifier.record_tool_outcome(
            tool_name="write_file",
            effective_args=args,
            effective_task_id="default",
            raw_result=json.dumps({"error": "second"}),
            dispatch=DispatchTriState.DISPATCHED,
            model_is_error=True,
            turn_generation=1,
        )

        failed = verifier.finalize_failed_dict()
        assert "retry.py" in failed
        assert "second" in failed["retry.py"]["error_preview"]


class TestLedgerOverflow:
    def test_exact_successful_retry_clears_all_overflowed_failures(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        paths = [f"file-{index}.txt" for index in range(65)]
        patch_lines = ["*** " + "Begin Patch"]
        for path in paths:
            patch_lines.extend((f"*** Add File: {path}", "+content"))
        patch_lines.append("*** " + "End Patch")
        args = {"mode": "patch", "patch": "\n".join(patch_lines)}
        verifier = TurnFileMutationVerifier(use_subprocess_fingerprint=False)
        verifier.reset_turn(1)

        verifier.record_tool_outcome(
            tool_name="patch",
            effective_args=args,
            effective_task_id="default",
            raw_result=json.dumps({"success": False, "error": "failed"}),
            dispatch=DispatchTriState.DISPATCHED,
            model_is_error=True,
            turn_generation=1,
        )
        assert "__overflow__" in verifier.finalize_failed_dict()

        verifier.record_tool_outcome(
            tool_name="patch",
            effective_args=args,
            effective_task_id="default",
            raw_result=json.dumps({"success": True, "files_modified": paths}),
            dispatch=DispatchTriState.DISPATCHED,
            model_is_error=False,
            turn_generation=1,
        )

        assert verifier.finalize_failed_dict() == {}


def _slow_fingerprint_worker(path_str, out_q):
    import time

    time.sleep(5)
    out_q.put((None, 0))


class TestFailsafeObservation:
    def test_subprocess_timeout_leaves_no_live_workers(self, tmp_path, monkeypatch):
        import agent.file_mutation_verifier as fmv

        target = tmp_path / "slow.bin"
        target.write_bytes(b"abc")

        monkeypatch.setattr(fmv, "_mp_fingerprint_worker", _slow_fingerprint_worker)
        monkeypatch.setattr(fmv, "OBSERVATION_TIMEOUT_S", 0.15)

        verifier = TurnFileMutationVerifier(use_subprocess_fingerprint=True)
        verifier.reset_turn(1)
        monkeypatch.chdir(tmp_path)
        fp = verifier._capture_baseline("slow.bin", "default", turn_generation=1)
        assert fp is None
        assert verifier.active_worker_pids == set()

    def test_resolved_credential_path_is_never_fingerprinted(
        self, tmp_path, monkeypatch,
    ):
        import agent.file_mutation_verifier as fmv

        hermes_home = tmp_path / "hermes-home"
        credential = hermes_home / "auth.json"
        credential.parent.mkdir()
        credential.write_text("dummy credential material\n", encoding="utf-8")
        process_cwd = tmp_path / "process-cwd"
        process_cwd.mkdir()

        monkeypatch.chdir(process_cwd)
        monkeypatch.setenv("HERMES_HOME", str(hermes_home))
        monkeypatch.setattr(
            fmv,
            "_resolve_local_path",
            lambda _raw_path, _task_id: credential,
        )

        def _fingerprint_must_not_run(*_args, **_kwargs):
            raise AssertionError("protected resolved path was fingerprinted")

        monkeypatch.setattr(
            fmv,
            "_stable_local_fingerprint",
            _fingerprint_must_not_run,
        )

        assert fmv._path_allowed_for_observation("auth.json")
        assert not fmv._path_allowed_for_observation(str(credential))

        verifier = TurnFileMutationVerifier(use_subprocess_fingerprint=False)
        verifier.reset_turn(1)
        assert verifier._capture_baseline(
            "auth.json",
            "credential-task",
            turn_generation=1,
        ) is None

    def test_symlink_is_not_observable(self, tmp_path):
        import os
        import time

        from agent.file_mutation_verifier import _stable_local_fingerprint_inprocess

        if os.name == "nt":
            pytest.skip("symlink lstat guard is POSIX-focused in this test")
        real = tmp_path / "real.txt"
        real.write_text("data\n", encoding="utf-8")
        link = tmp_path / "link.txt"
        link.symlink_to(real)
        fp, _ = _stable_local_fingerprint_inprocess(
            link, deadline=time.monotonic() + 5.0,
        )
        assert fp is None

    def test_torn_read_rejected(self, tmp_path, monkeypatch):
        import time

        from agent.file_mutation_verifier import _stable_local_fingerprint_inprocess

        target = tmp_path / "torn.txt"
        target.write_text("stable\n", encoding="utf-8")
        real_stat = target.stat()

        def _unstable_stat(path, *, follow_symlinks=True):
            if not follow_symlinks:
                raise OSError("simulated torn read")
            return real_stat

        monkeypatch.setattr(__import__("os"), "stat", _unstable_stat)
        fp, _ = _stable_local_fingerprint_inprocess(
            target, deadline=time.monotonic() + 5.0,
        )
        assert fp is None

    def test_posix_dialect_preserves_backslash_identity(self):
        verifier = TurnFileMutationVerifier(
            resolve_backend=lambda _tid: ("local", "host", "posix"),
        )
        a = verifier._identity_for_path("dir\\file.py", "default")
        b = verifier._identity_for_path("dir/file.py", "default")
        assert a is not None and b is not None
        assert a.path != b.path

    def test_ssh_backend_never_local_clears(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        target = tmp_path / "remote.py"
        target.write_text("a\n", encoding="utf-8")
        verifier = TurnFileMutationVerifier(
            resolve_backend=lambda _tid: ("ssh", "SSHSession", "posix"),
            use_subprocess_fingerprint=False,
        )
        verifier.reset_turn(1)
        verifier.record_tool_outcome(
            tool_name="write_file",
            effective_args={"path": "remote.py", "content": "b\n"},
            effective_task_id="default",
            raw_result=json.dumps({"error": "fail"}),
            dispatch=DispatchTriState.DISPATCHED,
            model_is_error=True,
            turn_generation=1,
        )
        target.write_text("b\n", encoding="utf-8")
        verifier.reconcile_content_transitions(task_id="default")
        assert "remote.py" in verifier.finalize_failed_dict()


class TestRegistryDispatchAuthority:
    def test_middleware_rewritten_file_args_drive_verifier_target(
        self, monkeypatch, tmp_path,
    ):
        monkeypatch.chdir(tmp_path)
        original = tmp_path / "original.txt"
        redirected = tmp_path / "redirected.txt"

        def _rewrite(name, args, execute, **kwargs):
            return execute({**args, "path": str(redirected)})

        def _failed_dispatch(name, args, **kwargs):
            Path(args["path"]).write_text("partial\n", encoding="utf-8")
            return json.dumps({"success": False, "error": "simulated failure"})

        monkeypatch.setattr(
            "hermes_cli.middleware.run_tool_execution_middleware",
            _rewrite,
        )
        monkeypatch.setattr("model_tools.registry.dispatch", _failed_dispatch)

        from model_tools import (
            begin_tool_registry_dispatch_tracking,
            end_tool_registry_dispatch_tracking,
            handle_function_call,
            tool_registry_dispatched_args,
        )

        verifier = TurnFileMutationVerifier(use_subprocess_fingerprint=False)
        verifier.reset_turn(1)

        def _prepare(dispatched_args):
            verifier.prepare_mutation_dispatch(
                tool_name="write_file",
                effective_args=dispatched_args,
                effective_task_id="default",
                turn_generation=1,
            )

        token = begin_tool_registry_dispatch_tracking(before_dispatch=_prepare)
        try:
            raw_result = handle_function_call(
                "write_file",
                {"path": str(original), "content": "requested\n"},
                task_id="default",
                skip_pre_tool_call_hook=True,
            )
            effective_args = tool_registry_dispatched_args()
        finally:
            end_tool_registry_dispatch_tracking(token)

        assert effective_args is not None
        verifier.record_tool_outcome(
            tool_name="write_file",
            effective_args=effective_args,
            effective_task_id="default",
            raw_result=raw_result,
            dispatch=DispatchTriState.DISPATCHED,
            model_is_error=True,
            turn_generation=1,
        )
        failed = verifier.finalize_failed_dict()
        assert str(redirected) in failed
        assert str(original) not in failed

    def test_handle_function_call_middleware_short_circuit_not_dispatched(
        self, monkeypatch, tmp_path,
    ):
        monkeypatch.chdir(tmp_path)

        def _short_circuit(name, args, execute, **kwargs):
            return json.dumps({"success": True, "bytes_written": 12})

        monkeypatch.setattr(
            "hermes_cli.middleware.run_tool_execution_middleware",
            _short_circuit,
        )
        from model_tools import (
            begin_tool_registry_dispatch_tracking,
            end_tool_registry_dispatch_tracking,
            handle_function_call,
            tool_registry_was_dispatched,
        )

        token = begin_tool_registry_dispatch_tracking()
        try:
            handle_function_call(
                "write_file",
                {"path": "never.txt", "content": "x"},
                task_id="default",
                skip_pre_tool_call_hook=True,
            )
            dispatched = tool_registry_was_dispatched()
        finally:
            end_tool_registry_dispatch_tracking(token)
        assert not dispatched

        agent = _bare_agent()
        agent._record_file_mutation_result(
            "patch",
            {"mode": "replace", "path": "a.txt", "old_string": "x", "new_string": "y"},
            json.dumps({"error": "first"}),
            is_error=True,
            raw_result=json.dumps({"error": "first"}),
            dispatch=DispatchTriState.DISPATCHED.value,
        )
        agent._record_file_mutation_result(
            "write_file",
            {"path": "never.txt", "content": "x"},
            json.dumps({"success": True, "bytes_written": 12}),
            is_error=False,
            dispatch=DispatchTriState.NOT_DISPATCHED.value,
        )
        sync_legacy_failed_state(agent)
        assert any(k.endswith("a.txt") for k in agent._turn_failed_file_mutations)

    def test_tracking_preserves_raw_registry_failure_after_middleware_transform(
        self, monkeypatch,
    ):
        raw_failure = json.dumps({"error": "disk failure"})
        visible_success = json.dumps({"bytes_written": 3, "path": "target.txt"})

        def _transform(_name, args, execute, **_kwargs):
            execute(args)
            return visible_success

        monkeypatch.setattr(
            "hermes_cli.middleware.run_tool_execution_middleware",
            _transform,
        )
        monkeypatch.setattr(
            "model_tools.registry.dispatch",
            lambda *_args, **_kwargs: raw_failure,
        )

        import model_tools

        token = model_tools.begin_tool_registry_dispatch_tracking(
            tool_name="write_file",
            tool_call_id="outer-call",
        )
        try:
            result = model_tools.handle_function_call(
                "write_file",
                {"path": "target.txt", "content": "new"},
                task_id="default",
                tool_call_id="outer-call",
                skip_pre_tool_call_hook=True,
            )
            captured = getattr(model_tools, "tool_registry_raw_result", lambda: None)()
        finally:
            model_tools.end_tool_registry_dispatch_tracking(token)

        assert result == visible_success
        assert captured == raw_failure

    def test_nested_dispatch_does_not_mark_short_circuited_outer_call(
        self, monkeypatch,
    ):
        nested_success = json.dumps({"bytes_written": 1, "path": "nested.txt"})

        def _reentrant(_name, args, execute, **_kwargs):
            if args.get("path") == "outer.txt":
                from model_tools import handle_function_call

                handle_function_call(
                    "write_file",
                    {"path": "nested.txt", "content": "n"},
                    task_id="default",
                    tool_call_id="nested-call",
                    skip_pre_tool_call_hook=True,
                )
                return json.dumps({"bytes_written": 1, "path": "outer.txt"})
            return execute(args)

        monkeypatch.setattr(
            "hermes_cli.middleware.run_tool_execution_middleware",
            _reentrant,
        )
        monkeypatch.setattr(
            "model_tools.registry.dispatch",
            lambda *_args, **_kwargs: nested_success,
        )

        from model_tools import (
            begin_tool_registry_dispatch_tracking,
            end_tool_registry_dispatch_tracking,
            handle_function_call,
            tool_registry_was_dispatched,
        )

        token = begin_tool_registry_dispatch_tracking(
            tool_name="write_file",
            tool_call_id="outer-call",
        )
        try:
            handle_function_call(
                "write_file",
                {"path": "outer.txt", "content": "o"},
                task_id="default",
                tool_call_id="outer-call",
                skip_pre_tool_call_hook=True,
            )
            dispatched = tool_registry_was_dispatched()
        finally:
            end_tool_registry_dispatch_tracking(token)

        assert not dispatched


class TestSingleReconciliation:
    def test_tool_finalization_reconciles_once(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        target = tmp_path / "once.txt"
        target.write_text("before\n", encoding="utf-8")
        agent = _bare_agent()
        verifier = agent._file_mutation_verifier
        original = verifier.reconcile_content_transitions
        verifier.reconcile_content_transitions = MagicMock(wraps=original)
        failure = json.dumps({"error": "failed"})

        from agent.tool_executor import _finalize_file_mutation_tool

        _finalize_file_mutation_tool(
            agent,
            tool_name="write_file",
            function_args={"path": "once.txt", "content": "after\n"},
            raw_result=failure,
            model_result=failure,
            is_error=True,
            blocked=False,
            registry_dispatched=True,
            result_missing=False,
            effective_task_id="default",
        )

        assert verifier.reconcile_content_transitions.call_count == 1


class TestWorkspaceIdentity:
    def test_configured_ssh_backend_is_nonlocal_before_environment_creation(
        self, monkeypatch,
    ):
        monkeypatch.setenv("TERMINAL_ENV", "ssh")
        monkeypatch.setattr("tools.terminal_tool.get_active_env", lambda _task_id: None)
        verifier = TurnFileMutationVerifier(use_subprocess_fingerprint=False)

        identity = verifier._identity_for_path("remote.txt", "fresh-ssh-task")

        assert identity is not None
        assert identity.backend_kind == "ssh"
        assert identity.path_dialect == "posix"

    def test_nonlocal_relative_identity_changes_with_backend_workspace(
        self, monkeypatch,
    ):
        class SSHEnvironment:
            cwd = "/workspace/a"

        env = SSHEnvironment()
        monkeypatch.setattr("tools.terminal_tool.get_active_env", lambda _task_id: env)
        verifier = TurnFileMutationVerifier(use_subprocess_fingerprint=False)

        first = verifier._identity_for_path("same.txt", "remote-task")
        env.cwd = "/workspace/b"
        second = verifier._identity_for_path("same.txt", "remote-task")

        assert first is not None and second is not None
        assert first.key() != second.key()

    def test_configured_nonlocal_identity_includes_workspace_before_creation(
        self, monkeypatch,
    ):
        monkeypatch.setenv("TERMINAL_ENV", "ssh")
        monkeypatch.setenv("TERMINAL_CWD", "/remote/a")
        monkeypatch.setattr("tools.terminal_tool.get_active_env", lambda _task_id: None)
        verifier = TurnFileMutationVerifier(use_subprocess_fingerprint=False)

        first = verifier._identity_for_path("same.txt", "fresh-ssh-task")
        monkeypatch.setenv("TERMINAL_CWD", "/remote/b")
        second = verifier._identity_for_path("same.txt", "fresh-ssh-task")

        assert first is not None and second is not None
        assert first.key() != second.key()

    def test_relative_identity_uses_local_environment_workspace(
        self, tmp_path, monkeypatch,
    ):
        process_cwd = tmp_path / "process"
        workspace = tmp_path / "workspace"
        process_cwd.mkdir()
        workspace.mkdir()
        monkeypatch.chdir(process_cwd)
        monkeypatch.setattr(
            "tools.file_tools._resolve_path_for_task",
            lambda raw_path, _task_id: (workspace / raw_path).resolve(),
        )
        verifier = TurnFileMutationVerifier(use_subprocess_fingerprint=False)

        identity = verifier._identity_for_path("relative.txt", "task-a")

        assert identity is not None
        assert Path(identity.path) == (workspace / "relative.txt").resolve()
