#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${ROOT_DIR}/.venv"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if [[ ! -d "${VENV_DIR}" ]]; then
  echo "[flavia] Creating venv at ${VENV_DIR}"
  "${PYTHON_BIN}" -m venv "${VENV_DIR}"
fi

"${VENV_DIR}/bin/python" -m pip install --upgrade pip
"${VENV_DIR}/bin/python" -m pip install -r "${ROOT_DIR}/requirements.lock"
"${VENV_DIR}/bin/python" -m pip install --no-deps -e "${ROOT_DIR}"

touch "${VENV_DIR}/.flavia_bootstrap_complete"

echo "[flavia] Installation complete."
echo "[flavia] Run with: ${VENV_DIR}/bin/flavia"
