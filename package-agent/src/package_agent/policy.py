from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Action:
    kind: str
    command: list[str]
    touches_project_files: bool = False


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str


ALLOWED_KINDS = {"inspect", "build", "env_repair", "artifact_collect"}
BLOCKED_GIT_COMMANDS = {"commit", "push", "pull", "tag"}
PROTECTED_PROJECT_PATTERNS = (
    "podfile",
    "pubspec.yaml",
    "fastfile",
    ".xcodeproj",
    ".xcworkspace",
    ".xcscheme",
    "project.pbxproj",
    "build.gradle",
    "build.gradle.kts",
    "settings.gradle",
    "settings.gradle.kts",
    "gradle.properties",
)


def evaluate_action(action: Action) -> PolicyDecision:
    if action.touches_project_files or action.kind == "project_modify":
        return PolicyDecision(False, "project_modification_blocked")
    if _contains_blocked_git_operation(action.command):
        return PolicyDecision(False, "blocked_git_operation")
    if _touches_protected_project_files(action.command):
        return PolicyDecision(False, "project_modification_blocked")
    if action.kind not in ALLOWED_KINDS:
        return PolicyDecision(False, "unknown_action_kind")
    return PolicyDecision(True, f"allowed_{action.kind}")


def _contains_blocked_git_operation(command: list[str]) -> bool:
    lowered = [token.lower() for token in command]
    if lowered[:1] == ["git"] and len(lowered) > 1 and lowered[1] in BLOCKED_GIT_COMMANDS:
        return True

    command_text = " ".join(lowered)
    return any(f"git {operation}" in command_text for operation in BLOCKED_GIT_COMMANDS)


def _touches_protected_project_files(command: list[str]) -> bool:
    command_text = " ".join(command).lower()
    return any(pattern in command_text for pattern in PROTECTED_PROJECT_PATTERNS)
