#!/usr/bin/env bash
# Bootstraps a local Python virtual environment for the Finance Tracker.
# Usage: ./scripts/setup_venv.sh

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON:-python3}"
VENV_PATH="${PROJECT_ROOT}/.venv"
REQUIREMENTS_FILE="${PROJECT_ROOT}/requirements.txt"

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "✗ Could not find ${PYTHON_BIN}. Set the PYTHON env var to a valid interpreter." >&2
  exit 1
fi

if [ ! -f "${REQUIREMENTS_FILE}" ]; then
  echo "✗ Missing requirements.txt at ${REQUIREMENTS_FILE}" >&2
  exit 1
fi

if [ -d "${VENV_PATH}" ]; then
  echo "• Reusing existing virtual environment at ${VENV_PATH}"
else
  echo "• Creating virtual environment at ${VENV_PATH}"
  "${PYTHON_BIN}" -m venv "${VENV_PATH}"
fi

# shellcheck disable=SC1090
source "${VENV_PATH}/bin/activate"

python -m pip install --upgrade pip
python -m pip install -r "${REQUIREMENTS_FILE}"

echo "\n✓ Virtual environment is ready. Activate it with:"
echo "   source ${VENV_PATH}/bin/activate"
echo "\nTo deactivate, run: deactivate"
