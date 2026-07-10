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

    exit_code = main(["build", "--input", str(input_path), "--output", str(tmp_path / "output")])

    assert exit_code == 0
