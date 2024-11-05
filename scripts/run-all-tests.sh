#!/bin/bash

# https://gist.github.com/mohanpedala/1e2ff5661761d3abd0385e8223e16425
set -e -x -v -u -o pipefail

SCRIPT_DIR=$(realpath "$(dirname "${BASH_SOURCE[0]}")")
source "${SCRIPT_DIR}/utilities/common.sh"

VENV_PATH="${PWD}/.cache/scripts/.cli-prod-venv" source "${PROJ_PATH}/scripts/utilities/ensure-venv.sh"
TOML=${PROJ_PATH}/pyproject.toml EXTRAS=cli,prod PIN=cli_prod_pinned \
  DEV_VENV_PATH="${PWD}/.cache/scripts/.venv" \
  TARGET_VENV_PATH="${PWD}/.cache/scripts/.cli-prod-venv" \
  bash "${PROJ_PATH}/scripts/utilities/ensure-reqs2.sh"

export PYTHONPATH=${PYTHONPATH:-}
export PYTHONPATH=${PYTHONPATH}:${PWD}

PG_PORT=$(python -c 'import socket; s = socket.socket(); s.bind(("", 0)); print(s.getsockname()[1]); s.close()')

PG_READY_FILE="${PWD}/.deleteme/pg_is_ready"
mkdir -p "$(dirname "${PG_READY_FILE}")"
[[ -f "${PG_READY_FILE}" ]] && rm -f "${PG_READY_FILE}"

PG_PID=
PG_READY_FILE="${PG_READY_FILE}" \
PG_PORT="${PG_PORT}" \
PG_USER=user \
PG_PWD=password \
PG_SUPER_PWD=123 \
PG_DB_NAME=db-name \
PG_DOCKER_NAME=fulcrum-test-pg-instance \
bash scripts/pg.sh & PG_PID=$!

function cleanup {
  if [[ -n "${PG_PID}" ]]; then
    # Kill the postgres instance and its children
    pkill -P "${PG_PID}" || true
    sleep 1
    # If they didn't die, kill it with fire
    pkill --signal 9 -P "${PG_PID}" || true
    sleep 1
    # If they still didn't die, kill it with fire
    kill -9 "${PG_PID}" || true
  fi
}
trap cleanup EXIT

# Wait until PG_READY_FILE exists
while [[ ! -f "${PG_READY_FILE}" ]]; do
  sleep 1
done

export FULCRUM_TEST_DSN="postgresql+asyncpg://user:password@127.0.0.1:${PG_PORT}/db-name"

# Find all files in comfy_fulcrum that end in _test.py
find comfy_fulcrum -name "*_test.py" | while read -r TEST_FILE; do
  TEST_MODULE=$(echo "${TEST_FILE}" | sed -e 's/\//./g' -e 's/\.py$//')
  python -m "${TEST_MODULE}"
done

find comfy_fulcrum -name "*_test.sh" -print0 | while IFS= read -r -d '' TEST_FILE; do
  echo -e "${YELLOW}Running ${TEST_FILE}${NC}"
  bash "${TEST_FILE}"
  echo -e "${GREEN}${TEST_FILE} ran successfully${NC}"
done

# Includes long-running tests.
# TODO: Use a proper testing framework that will run these in parallel.
find tests/ -name "*_test.py" | while read -r TEST_FILE; do
  python "${TEST_FILE}"
done

echo -e "${GREEN}All tests ran successfully${NC}"
