from __future__ import annotations

from types import SimpleNamespace

from package_agent.llm_discovery import LlmAdapter
from package_agent.llm_planner import planner_command, request_llm_plan
from package_agent.models import BuildInput


def test_planner_command_uses_stdin_for_injected_planner() -> None:
    command = planner_command(LlmAdapter(name="injected_llm_planner", executable="/tmp/fake"), "prompt")

    assert command.args == ["/tmp/fake"]
    assert command.stdin == "prompt"


def test_planner_command_uses_codex_exec_json() -> None:
    command = planner_command(LlmAdapter(name="codex_cli", executable="/usr/bin/codex"), "prompt")

    assert command.args == ["/usr/bin/codex", "exec", "--json"]
    assert command.stdin == "prompt"


def test_planner_command_uses_claude_prompt_flag() -> None:
    command = planner_command(LlmAdapter(name="claude_cli", executable="/usr/bin/claude"), "prompt")

    assert command.args == ["/usr/bin/claude", "-p", "prompt"]
    assert command.stdin is None


def test_planner_command_uses_llm_runtime_json_protocol() -> None:
    command = planner_command(LlmAdapter(name="llm_runtime", executable="/usr/bin/llm-runtime"), "prompt")

    assert command.args == ["/usr/bin/llm-runtime", "package-agent-plan-json"]
    assert command.stdin == "prompt"


def test_request_llm_plan_passes_adapter_specific_invocation(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_run(args, **kwargs):  # type: ignore[no-untyped-def]
        captured["args"] = args
        captured["input"] = kwargs.get("input")
        return SimpleNamespace(returncode=0, stdout='{"actions":[{"kind":"inspect"}]}')

    monkeypatch.setattr("package_agent.llm_planner.subprocess.run", fake_run)

    plan = request_llm_plan(
        LlmAdapter(name="claude_cli", executable="/usr/bin/claude"),
        BuildInput(
            project_dir="/tmp/project",
            platform="ios",
            environment="development",
            artifact_type="ipa",
        ),
    )

    assert len(plan.actions) == 1
    assert captured["args"][0:2] == ["/usr/bin/claude", "-p"]
    assert isinstance(captured["args"][2], str)
    assert '"projectDir": "/tmp/project"' in captured["args"][2]
    assert captured["input"] is None
