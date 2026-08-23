#!/bin/zsh
set -euo pipefail

REPO_DIR="${0:A:h:h}"
cd "${REPO_DIR}"

if [[ ! -x "${REPO_DIR}/.venv/bin/python" ]]; then
  echo "Missing ${REPO_DIR}/.venv. Create the project virtual environment first." >&2
  exit 2
fi
if [[ ! -f "${REPO_DIR}/.env" ]]; then
  echo "Missing ${REPO_DIR}/.env. Refusing to start without local credentials." >&2
  exit 2
fi

set -a
source "${REPO_DIR}/.env"
set +a

exec "${REPO_DIR}/.venv/bin/douban-weread-feishu"
