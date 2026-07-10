from __future__ import annotations

import json
import shlex
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from package_agent.llm_discovery import LlmAdapter
from package_agent.models import BuildInput


@dataclass(frozen=True)
class PlanAction:
    kind: str
    command: list[str] = field(default_factory=list)
    package_paths: list[str] = field(default_factory=list)
    symbols_paths: list[str] = field(default_factory=list)
    log_paths: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class LlmPlan:
    actions: list[PlanAction]


@dataclass(frozen=True)
class PlannerCommand:
    args: list[str]
    stdin: str | None


def request_llm_plan(
    adapter: LlmAdapter,
    build_input: BuildInput,
    *,
    timeout_seconds: int = 120,
) -> LlmPlan:
    command = planner_command(adapter, _planner_prompt(build_input))
    result = subprocess.run(
        command.args,
        input=command.stdin,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError(f"planner exited with code {result.returncode}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("planner did not return valid JSON") from exc
    return parse_llm_plan(payload)


def planner_command(adapter: LlmAdapter, prompt: str) -> PlannerCommand:
    if adapter.name == "injected_llm_planner":
        return PlannerCommand(args=[adapter.executable], stdin=prompt)
    if adapter.name == "codex_cli":
        return PlannerCommand(args=[adapter.executable, "exec", "--json"], stdin=prompt)
    if adapter.name == "claude_cli":
        return PlannerCommand(args=[adapter.executable, "-p", prompt], stdin=None)
    if adapter.name == "llm_runtime":
        # Local contract: `llm-runtime package-agent-plan-json` reads the JSON prompt from
        # stdin and returns only plan JSON on stdout.
        return PlannerCommand(
            args=[adapter.executable, "package-agent-plan-json"],
            stdin=prompt,
        )
    return PlannerCommand(args=[adapter.executable], stdin=prompt)


def parse_llm_plan(payload: object) -> LlmPlan:
    if not isinstance(payload, dict):
        raise ValueError("planner JSON must be an object")
    raw_actions = payload.get("actions")
    if not isinstance(raw_actions, list) or not raw_actions:
        raise ValueError("planner JSON must include non-empty actions")
    return LlmPlan(actions=[_parse_action(item) for item in raw_actions])


def _parse_action(payload: object) -> PlanAction:
    if not isinstance(payload, dict):
        raise ValueError("planner action must be an object")
    kind = payload.get("kind")
    if not isinstance(kind, str) or not kind.strip():
        raise ValueError("planner action kind must be a non-empty string")
    return PlanAction(
        kind=kind.strip(),
        command=_parse_command(payload.get("command")),
        package_paths=_string_list(payload.get("packagePaths")),
        symbols_paths=_string_list(payload.get("symbolsPaths")),
        log_paths=_string_list(payload.get("logPaths")),
    )


def _parse_command(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list) and all(isinstance(item, str) and item for item in value):
        return list(value)
    if isinstance(value, str) and value.strip():
        return shlex.split(value)
    raise ValueError("planner action command must be a string or string array")


def _string_list(value: object) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError("planner artifact paths must be string arrays")
    return list(value)


def _planner_prompt(build_input: BuildInput) -> str:
    payload: dict[str, Any] = {
        "task": "Return only JSON for a constrained TestFlying package-agent build plan.",
        "schema": {
            "actions": [
                {
                    "kind": "inspect|build|env_repair|artifact_collect",
                    "command": ["executable", "arg"],
                    "packagePaths": ["relative/glob/*.ipa"],
                    "symbolsPaths": ["relative/glob/*.zip"],
                    "logPaths": ["relative/glob/*.log"],
                }
            ]
        },
        "constraints": [
            "Do not modify protected project source, build scripts, git history, or credentials.",
            "Use commands that can pass package_agent.policy.evaluate_action.",
            "Collect package, symbols, and log artifacts with paths relative to projectDir.",
        ],
        "buildInput": {
            "projectDir": str(Path(build_input.project_dir)),
            "platform": build_input.platform,
            "environment": build_input.environment,
            "artifactType": build_input.artifact_type,
            "gitRef": build_input.git_ref,
            "repoSubpath": build_input.repo_subpath,
        },
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)
