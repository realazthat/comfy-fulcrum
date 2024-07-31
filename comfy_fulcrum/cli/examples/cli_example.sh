#!/bin/bash
# https://gist.github.com/mohanpedala/1e2ff5661761d3abd0385e8223e16425
set -e -x -v -u -o pipefail

GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'


PG_PID=
SERVER_PID=
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
  if [[ -n "${SERVER_PID}" ]]; then
    murder_process "${SERVER_PID}" || true
  fi
  if [[ -n "${PG_PID}" ]]; then
    murder_process "${PG_PID}" || true
  fi
  if [[ -n "${TMP_DIR}" ]]; then
    rm -Rf "${TMP_DIR}" || true
  fi
}
trap 'cleanup > /dev/null 2>&1 || true' EXIT 

TMP_DIR=$(mktemp -d)
PG_PORT=$(python -c 'import socket; s = socket.socket(); s.bind(("", 0)); print(s.getsockname()[1]); s.close()')
FULCRUM_PORT=$(python -c 'import socket; s = socket.socket(); s.bind(("", 0)); print(s.getsockname()[1]); s.close()')
PG_DIR="${TMP_DIR}/.data/pgdata"
mkdir -p "${PG_DIR}"


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

(
# SERVER_SNIPPET_START
python -m comfy_fulcrum.cli server \
  --dsn "${DSN}" \
  --host 0.0.0.0 --port "${FULCRUM_PORT}"
# SERVER_SNIPPET_END
) & SERVER_PID=$!
FULCRUM_API_URL="http://127.0.0.1:${FULCRUM_PORT}"

# Wait until curl can get the /docs page, or the PID is down.
while true; do
  echo -e "${BLUE}Wait until fulcrum server is ready${NC}"
  if curl -s "${FULCRUM_API_URL}/docs" > /dev/null; then
    echo "Server is up and running."
    break
  elif ! kill -0 $SERVER_PID 2> /dev/null; then
    echo "Server process has terminated unexpectedly."
    exit 1
  fi
  sleep 1
done

# CLIENT_SNIPPET_START
python -m comfy_fulcrum.cli client \
  --fulcrum_api_url "${FULCRUM_API_URL}" \
  --data '' \
  stats

RESOURCE_A_ID=a
python -m comfy_fulcrum.cli client \
  --fulcrum_api_url "${FULCRUM_API_URL}" \
  --data '{"resource_id": "'"${RESOURCE_A_ID}"'","channels": ["main"], "data": "{\"comfy_api_url\": \"url\"}"}' \
  register

python -m comfy_fulcrum.cli client \
  --fulcrum_api_url "${FULCRUM_API_URL}" \
  list

python -m comfy_fulcrum.cli client \
  --fulcrum_api_url "${FULCRUM_API_URL}" \
  --data '' \
  stats

TICKET=$(python -m comfy_fulcrum.cli client \
  --fulcrum_api_url "${FULCRUM_API_URL}" \
  --data '{"client_name": "me","channels": ["main"], "priority": "1"}' \
  get)

# Example TICKET:
# {"id": "4fe26e1fe5974e68b788f82cc9460b0b", "client_name": "me", "lease_timeout": 180.0, "ends": "2024-07-21T01:18:16.317032"}
echo "TICKET: ${TICKET}"

TICKET_ID=$(echo "${TICKET}" | jq -r '.id')
echo "TICKET_ID: ${TICKET_ID}"

RESOURCE_ID=
while [[ -z "${RESOURCE_ID}" ]]; do
  echo -e "${BLUE}Checking if resource is ready${NC}"
  TICKET=$(python -m comfy_fulcrum.cli client \
    --fulcrum_api_url "${FULCRUM_API_URL}" \
    --data '{"id": "'"${TICKET_ID}"'"}' \
    touch)
  echo "TICKET: ${TICKET}"
  RESOURCE_ID=$(echo "${TICKET}" | jq -r '.resource_id')
  echo "RESOURCE_ID: ${RESOURCE_ID}"
  sleep 2
done

RESOURCE_DATA=$(echo "${TICKET}" | jq -r '.data')
COMFY_API_URL=$(echo "${RESOURCE_DATA}" | jq -r '.comfy_api_url')

echo -e "${BLUE}COMFY_API_URL: ${COMFY_API_URL}${NC}"

python -m comfy_fulcrum.cli client \
  --fulcrum_api_url "${FULCRUM_API_URL}" \
  --data '' \
  stats

sleep 2
python -m comfy_fulcrum.cli client \
  --fulcrum_api_url "${FULCRUM_API_URL}" \
  --data '{"id": "'"${TICKET_ID}"'", "report": "success", "report_extra": {}}' \
  release

python -m comfy_fulcrum.cli client \
  --fulcrum_api_url "${FULCRUM_API_URL}" \
  --data '{"resource_id": "'"${RESOURCE_A_ID}"'"}' \
  remove

python -m comfy_fulcrum.cli client \
  --fulcrum_api_url "${FULCRUM_API_URL}" \
  --data '' \
  stats
# CLIENT_SNIPPET_END

echo -e "${GREEN}Example ran successfully${NC}"
