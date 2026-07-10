from __future__ import annotations

import json
from pathlib import Path

from package_agent.cli import main


def test_cli_writes_report_and_returns_needs_human_for_missing_input(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"

    exit_code = main(
        ["build", "--input", str(tmp_path / "missing.json"), "--output", str(output_dir)]
    )

    assert exit_code == 2
    report = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))
    assert report["status"] == "needs_human"
    assert report["classification"] == "missing_input"


def test_cli_returns_failed_for_invalid_json(tmp_path: Path) -> None:
    input_path = tmp_path / "build-input.json"
    input_path.write_text("{not-json", encoding="utf-8")
    output_dir = tmp_path / "output"

    exit_code = main(["build", "--input", str(input_path), "--output", str(output_dir)])

    assert exit_code == 1
    report = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))
    assert report["status"] == "failed"
    assert report["classification"] == "invalid_input_json"


def test_cli_returns_failed_for_non_object_json(tmp_path: Path) -> None:
    input_path = tmp_path / "build-input.json"
    input_path.write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")
    output_dir = tmp_path / "output"

    exit_code = main(["build", "--input", str(input_path), "--output", str(output_dir)])

    assert exit_code == 1
    report = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))
    assert report["status"] == "failed"
    assert report["classification"] == "invalid_input_shape"


def test_cli_returns_failed_for_missing_required_fields(tmp_path: Path) -> None:
    input_path = tmp_path / "build-input.json"
    input_path.write_text(
        json.dumps(
            {
                "projectDir": str(tmp_path / "project"),
                "platform": "ios",
                "environment": "prod",
            }
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "output"

    exit_code = main(["build", "--input", str(input_path), "--output", str(output_dir)])

    assert exit_code == 1
    report = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))
    assert report["status"] == "failed"
    assert report["classification"] == "invalid_input"
    assert "artifactType" in report["summary"]


def test_cli_returns_failed_for_invalid_artifact_lists(tmp_path: Path) -> None:
    input_path = tmp_path / "build-input.json"
    input_path.write_text(
        json.dumps(
            {
                "projectDir": str(tmp_path / "project"),
                "platform": "ios",
                "environment": "prod",
                "artifactType": "ipa",
                "packagePaths": "app.ipa",
            }
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "output"

    exit_code = main(["build", "--input", str(input_path), "--output", str(output_dir)])

    assert exit_code == 1
    report = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))
    assert report["status"] == "failed"
    assert report["classification"] == "invalid_input"
    assert "string lists" in report["summary"]


def test_cli_returns_failed_for_max_attempts_above_retry_cap(tmp_path: Path) -> None:
    input_path = tmp_path / "build-input.json"
    input_path.write_text(
        json.dumps(
            {
                "projectDir": str(tmp_path / "project"),
                "platform": "ios",
                "environment": "prod",
                "artifactType": "ipa",
                "maxAttempts": 6,
            }
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "output"

    exit_code = main(["build", "--input", str(input_path), "--output", str(output_dir)])

    assert exit_code == 1
    report = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))
    assert report["status"] == "failed"
    assert report["classification"] == "invalid_input"
    assert report["summary"] == "maxAttempts must be <= 5"


def test_cli_returns_failed_for_boolean_max_attempts(tmp_path: Path) -> None:
    input_path = tmp_path / "build-input.json"
    input_path.write_text(
        json.dumps(
            {
                "projectDir": str(tmp_path / "project"),
                "platform": "ios",
                "environment": "prod",
                "artifactType": "ipa",
                "maxAttempts": True,
            }
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "output"

    exit_code = main(["build", "--input", str(input_path), "--output", str(output_dir)])

    assert exit_code == 1
    report = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))
    assert report["status"] == "failed"
    assert report["classification"] == "invalid_input"
    assert report["summary"] == "maxAttempts must be a positive integer when provided"


def test_cli_returns_success_only_with_required_artifacts(tmp_path: Path) -> None:
    package_path = tmp_path / "app.ipa"
    symbols_path = tmp_path / "app.dsym.zip"
    log_path = tmp_path / "build.log"
    for path in (package_path, symbols_path, log_path):
        path.write_text("artifact", encoding="utf-8")
    input_path = tmp_path / "build-input.json"
    input_path.write_text(
        json.dumps(
            {
                "projectDir": str(tmp_path / "project"),
                "platform": "ios",
                "environment": "prod",
                "artifactType": "ipa",
                "packagePaths": [str(package_path)],
                "symbolsPaths": [str(symbols_path)],
                "logPaths": [str(log_path)],
            }
        ),
        encoding="utf-8",
    )

    output_dir = tmp_path / "output"
    exit_code = main(["build", "--input", str(input_path), "--output", str(output_dir)])

    assert exit_code == 0
    report = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))
    assert report["status"] == "success"
    assert report["classification"] == "build_succeeded"
