#!/bin/bash
# https://gist.github.com/mohanpedala/1e2ff5661761d3abd0385e8223e16425
set -e -x -v -u -o pipefail

GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'


PG_PID=
TMP_DIR=

function murder_process {
  PID=$1
  
  if [[ -n "${PID}" ]]; then
    # Kill the process and its children.
    pkill -P "${PID}" || true
    sleep 1
    # If they didn't die, kill it with fire.
    pkill --signal 9 -P "${PID}" || true
    sleep 1
    # Nicely ask the process to die
    kill -SIGINT "${PID}" || true
    sleep 1
    # If the process itself didn't die, kill it with fire.
    kill -9 "${PID}" || true
  fi
}

function cleanup {
  if [[ -n "${PG_PID}" ]]; then
    murder_process "${PG_PID}" || true
  fi
  if [[ -n "${TMP_DIR}" ]]; then
    rm -Rf "${TMP_DIR}" || true
  fi
}
trap 'cleanup > /dev/null 2>&1 || true' EXIT


TMP_DIR=$(mktemp -d)
PG_DIR="${TMP_DIR}/.data/pgdata"
PG_PORT=$(python -c 'import socket; s = socket.socket(); s.bind(("", 0)); print(s.getsockname()[1]); s.close()')

PG_READY_FILE="${TMP_DIR}/.deleteme/pg_is_ready"
mkdir -p "$(dirname "${PG_READY_FILE}")"
[[ -f "${PG_READY_FILE}" ]] && rm -f "${PG_READY_FILE}"

PG_READY_FILE="${PG_READY_FILE}" \
PG_DIR="${PG_DIR}" \
PG_PORT="${PG_PORT}" \
PG_USER=user \
PG_PWD=password \
PG_SUPER_PWD=123 \
PG_DB_NAME=db-name \
PG_DOCKER_NAME=fulcrum-test-pg-instance \
bash scripts/pg.sh > /dev/null 2>&1 & PG_PID=$!


# Wait until PG_READY_FILE exists
while [[ ! -f "${PG_READY_FILE}" ]]; do
  echo -e "${BLUE}Waiting for PG to be ready${NC}"
  sleep 1
done

DSN="postgresql+asyncpg://user:password@127.0.0.1:${PG_PORT}/db-name"
export DSN
python -m examples.python_example

echo -e "${GREEN}Example ran successfully${NC}"
