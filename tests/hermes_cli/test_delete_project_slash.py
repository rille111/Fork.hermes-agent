"""Regression tests for the removed, incomplete /delete-project command."""

from __future__ import annotations

from hermes_cli.commands import resolve_command


def test_delete_project_command_is_not_registered():
    assert resolve_command("delete-project") is None
    assert resolve_command("deleteproject") is None
    assert resolve_command("rmproject") is None


def test_tui_gateway_does_not_route_delete_project_to_agent():
    from tui_gateway import server

    response = server._methods["command.dispatch"](
        1,
        {"name": "delete-project", "arg": "", "session_id": ""},
    )

    assert response["error"]["code"] == 4018
    assert "not a quick/plugin/bundle/skill command" in response["error"]["message"]


def test_tui_gateway_pending_commands_exclude_delete_project():
    from tui_gateway.server import _PENDING_INPUT_COMMANDS

    assert not {"delete-project", "deleteproject", "rmproject"} & _PENDING_INPUT_COMMANDS
