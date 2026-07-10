from __future__ import annotations

import argparse
import json
from pathlib import Path

from package_agent.llm_discovery import discover_llm_adapter
from package_agent.models import AgentReport, BuildInput, classify_build


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="package-agent")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_parser = subparsers.add_parser("build")
    build_parser.add_argument("--input", required=True)
    build_parser.add_argument("--output", required=True)

    args = parser.parse_args(argv)
    if args.command != "build":
        parser.error(f"unsupported command: {args.command}")

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    report = _build_report(Path(args.input))
    _write_report(output_dir=output_dir, report=report)
    return report.exit_code()


def _build_report(input_path: Path) -> AgentReport:
    if not input_path.exists():
        return AgentReport(
            status="needs_human",
            classification="missing_input",
            summary="Build input JSON does not exist.",
        )

    try:
        payload = json.loads(input_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return AgentReport(
            status="failed",
            classification="invalid_input_json",
            summary="Build input is not valid JSON.",
        )

    if not isinstance(payload, dict):
        return AgentReport(
            status="failed",
            classification="invalid_input_shape",
            summary="Build input JSON must be an object.",
        )

    try:
        build_input = BuildInput.from_dict(payload)
    except ValueError as exc:
        return AgentReport(
            status="failed",
            classification="invalid_input",
            summary=str(exc),
        )

    adapter = discover_llm_adapter()
    return classify_build(build_input=build_input, adapter_name=adapter.name if adapter else None)


def _write_report(output_dir: Path, report: AgentReport) -> None:
    report_path = output_dir / "report.json"
    report_payload = json.dumps(report.to_dict(), ensure_ascii=False, indent=2)
    report_path.write_text(report_payload, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
