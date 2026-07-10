from __future__ import annotations

from package_agent.policy import Action, PolicyDecision, evaluate_action


def test_policy_allows_environment_repair_command() -> None:
    action = Action(
        kind="env_repair",
        command=["flutter", "pub", "get"],
        touches_project_files=False,
    )

    decision = evaluate_action(action)

    assert decision == PolicyDecision(allowed=True, reason="allowed_env_repair")


def test_policy_blocks_project_modification() -> None:
    action = Action(
        kind="project_modify",
        command=["python3", "-c", "open('pubspec.yaml','w')"],
        touches_project_files=True,
    )

    decision = evaluate_action(action)

    assert decision.allowed is False
    assert decision.reason == "project_modification_blocked"


def test_policy_blocks_git_push() -> None:
    action = Action(kind="inspect", command=["git", "push", "origin", "main"])

    decision = evaluate_action(action)

    assert decision == PolicyDecision(allowed=False, reason="blocked_git_operation")


def test_policy_blocks_shell_wrapped_git_commit() -> None:
    action = Action(kind="inspect", command=["bash", "-lc", "git commit -m test"])

    decision = evaluate_action(action)

    assert decision == PolicyDecision(allowed=False, reason="blocked_git_operation")


def test_policy_blocks_protected_build_file_change() -> None:
    action = Action(
        kind="env_repair",
        command=["python3", "-c", "open('ios/Podfile','w').write('platform :ios')"],
    )

    decision = evaluate_action(action)

    assert decision == PolicyDecision(allowed=False, reason="project_modification_blocked")


def test_policy_blocks_build_action_that_writes_source_file() -> None:
    action = Action(
        kind="build",
        command=["python3", "-c", "open('lib/main.dart','w').write('// rewritten')"],
    )

    decision = evaluate_action(action)

    assert decision == PolicyDecision(allowed=False, reason="project_modification_blocked")


def test_policy_blocks_env_repair_that_writes_source_directory() -> None:
    action = Action(
        kind="env_repair",
        command=["cp", "/tmp/generated.dart", "src/generated/app.dart"],
    )

    decision = evaluate_action(action)

    assert decision == PolicyDecision(allowed=False, reason="project_modification_blocked")


def test_policy_blocks_build_script_rewrite() -> None:
    action = Action(
        kind="build",
        command=["bash", "-lc", "echo '#!/bin/sh' > scripts/build.sh"],
    )

    decision = evaluate_action(action)

    assert decision == PolicyDecision(allowed=False, reason="project_modification_blocked")


def test_policy_allows_git_status_for_inspection() -> None:
    action = Action(kind="inspect", command=["git", "status", "--short"])

    decision = evaluate_action(action)

    assert decision == PolicyDecision(allowed=True, reason="allowed_inspect")
