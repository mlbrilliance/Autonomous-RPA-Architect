#!/usr/bin/env bash
# Install .NET 8 SDK and UiPath.CLI in the user home directory.
#
# Usage: bash scripts/install_uipath_cli.sh
#
# Notes:
#   - The Linux build of UiPath.CLI 25.10 (uipath.cli.linux) cannot pack
#     projects with `targetFramework: "Windows"` due to a hard-coded check
#     ('Cannot execute Windows projects on Linux platform'). Use the
#     manual_packager fallback baked into rpa_architect.assembler.packager
#     for Linux/CI builds. This script still installs the CLI for users
#     who want to validate or analyse projects.
#   - On Windows or macOS, the script switches to UiPath.CLI.Windows /
#     UiPath.CLI.Macos automatically.

set -euo pipefail

DOTNET_ROOT="${HOME}/.dotnet"

if ! command -v dotnet >/dev/null 2>&1; then
  echo "[install] downloading dotnet-install.sh"
  curl -sSL https://dot.net/v1/dotnet-install.sh -o /tmp/dotnet-install.sh
  chmod +x /tmp/dotnet-install.sh
  /tmp/dotnet-install.sh --channel 8.0 --install-dir "${DOTNET_ROOT}"
fi

export DOTNET_ROOT
export PATH="${DOTNET_ROOT}:${DOTNET_ROOT}/tools:${PATH}"

case "$(uname -s)" in
  Linux*)  TOOL_ID="UiPath.CLI.Linux" ;;
  Darwin*) TOOL_ID="UiPath.CLI.Macos" ;;
  *)       TOOL_ID="UiPath.CLI.Windows" ;;
esac

if ! command -v uipcli >/dev/null 2>&1; then
  echo "[install] installing ${TOOL_ID}"
  dotnet tool install --global "${TOOL_ID}" --version 25.10.12
fi

echo
echo "[install] versions:"
"${DOTNET_ROOT}/dotnet" --version
"${DOTNET_ROOT}/tools/uipcli" --help | head -3 || true

cat <<'EOF'

[install] To use the CLI in this shell, run:
    export DOTNET_ROOT=$HOME/.dotnet
    export PATH=$HOME/.dotnet:$HOME/.dotnet/tools:$PATH

For day-to-day use, the rpa_architect.assembler.packager module will fall
back to the manual_packager (Python zipfile) when uipcli is unavailable
or refuses to pack a Windows-targeted project on Linux.
EOF
