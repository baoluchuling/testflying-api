#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
RUNNER_DIR="${REPO_ROOT}/build-runner"
PACKAGING_DIR="${RUNNER_DIR}/packaging"
CONFIG_SOURCE="${1:-}"
OUTPUT_DIR="${2:-${REPO_ROOT}/outputs/build-runner-installer}"
STAGING_DIR="${OUTPUT_DIR}/build-runner-macos"

mkdir -p "${STAGING_DIR}"

(
  cd "${RUNNER_DIR}"
  go build -o "${STAGING_DIR}/testflying-build-runner" ./cmd/testflying-build-runner
)

if [[ -n "${CONFIG_SOURCE}" ]]; then
  cp "${CONFIG_SOURCE}" "${STAGING_DIR}/config.json"
else
  cat > "${STAGING_DIR}/config.json" <<'EOF'
{
  "runnerId": "",
  "name": "",
  "token": "",
  "serverUrl": "http://127.0.0.1:8000",
  "rootDir": "",
  "packageAgentBin": "",
  "version": "dev",
  "packageAgentVersion": "dev",
  "labels": ["ios-release"],
  "platforms": ["ios"],
  "llmAdapters": ["codex"],
  "capacity": 1
}
EOF
fi

cp "${PACKAGING_DIR}/install.command" "${STAGING_DIR}/install.command"
chmod +x "${STAGING_DIR}/install.command" "${STAGING_DIR}/testflying-build-runner"

printf 'Build runner installer staged at %s\n' "${STAGING_DIR}"
