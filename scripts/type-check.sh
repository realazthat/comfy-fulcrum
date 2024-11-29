#!/bin/bash
# https://gist.github.com/mohanpedala/1e2ff5661761d3abd0385e8223e16425
set -e -x -v -u -o pipefail

SCRIPT_DIR=$(realpath "$(dirname "${BASH_SOURCE[0]}")")
source "${SCRIPT_DIR}/utilities/common.sh"

VENV_PATH="${PWD}/.cache/scripts/.cli-dev-venv" source "${PROJ_PATH}/scripts/utilities/ensure-venv.sh"
TOML="${PROJ_PATH}/pyproject.toml" EXTRAS=cli,dev PIN=cli_dev_pinned \
  DEV_VENV_PATH="${PWD}/.cache/scripts/.venv" \
  TARGET_VENV_PATH="${PWD}/.cache/scripts/.cli-dev-venv" \
  bash "${PROJ_PATH}/scripts/utilities/ensure-reqs2.sh"

python -m mypy "${PROJ_PATH}/comfy_fulcrum/" --check-untyped-defs --show-error-codes
python3 -m pyright --stats "${PROJ_PATH}/comfy_fulcrum/"

VENV_PATH="${PWD}/.cache/scripts/.db-dev-venv" source "${PROJ_PATH}/scripts/utilities/ensure-venv.sh"
TOML="${PROJ_PATH}/pyproject.toml" EXTRAS=db,dev PIN=db_dev_pinned \
  DEV_VENV_PATH="${PWD}/.cache/scripts/.venv" \
  TARGET_VENV_PATH="${PWD}/.cache/scripts/.db-dev-venv" \
  bash "${PROJ_PATH}/scripts/utilities/ensure-reqs2.sh"

python -m mypy "${PROJ_PATH}/comfy_fulcrum/db" "${PROJ_PATH}/comfy_fulcrum/base" "${PROJ_PATH}/comfy_fulcrum/private" --check-untyped-defs --show-error-codes
python3 -m pyright --stats "${PROJ_PATH}/comfy_fulcrum/db" "${PROJ_PATH}/comfy_fulcrum/base" "${PROJ_PATH}/comfy_fulcrum/private"


VENV_PATH="${PWD}/.cache/scripts/.fastapi_client-dev-venv" source "${PROJ_PATH}/scripts/utilities/ensure-venv.sh"
TOML="${PROJ_PATH}/pyproject.toml" EXTRAS=fastapi_client,dev PIN=fastapi_client_dev_pinned \
  DEV_VENV_PATH="${PWD}/.cache/scripts/.venv" \
  TARGET_VENV_PATH="${PWD}/.cache/scripts/.fastapi_client-dev-venv" \
  bash "${PROJ_PATH}/scripts/utilities/ensure-reqs2.sh"

python -m mypy "${PROJ_PATH}/comfy_fulcrum/fastapi_client" "${PROJ_PATH}/comfy_fulcrum/base" "${PROJ_PATH}/comfy_fulcrum/private" --check-untyped-defs --show-error-codes
python3 -m pyright --stats "${PROJ_PATH}/comfy_fulcrum/fastapi_client" "${PROJ_PATH}/comfy_fulcrum/base" "${PROJ_PATH}/comfy_fulcrum/private"


VENV_PATH="${PWD}/.cache/scripts/.fastapi_server-dev-venv" source "${PROJ_PATH}/scripts/utilities/ensure-venv.sh"
TOML="${PROJ_PATH}/pyproject.toml" EXTRAS=fastapi_server,dev PIN=fastapi_server_dev_pinned \
  DEV_VENV_PATH="${PWD}/.cache/scripts/.venv" \
  TARGET_VENV_PATH="${PWD}/.cache/scripts/.fastapi_server-dev-venv" \
  bash "${PROJ_PATH}/scripts/utilities/ensure-reqs2.sh"

python -m mypy "${PROJ_PATH}/comfy_fulcrum/fastapi_server" "${PROJ_PATH}/comfy_fulcrum/base" "${PROJ_PATH}/comfy_fulcrum/private" --check-untyped-defs --show-error-codes
python3 -m pyright --stats "${PROJ_PATH}/comfy_fulcrum/fastapi_server" "${PROJ_PATH}/comfy_fulcrum/base" "${PROJ_PATH}/comfy_fulcrum/private"


VENV_PATH="${PWD}/.cache/scripts/.fastapi_mgmt_ui-dev-venv" source "${PROJ_PATH}/scripts/utilities/ensure-venv.sh"
TOML="${PROJ_PATH}/pyproject.toml" EXTRAS=fastapi_mgmt_ui,dev PIN=fastapi_mgmt_ui_dev_pinned \
  DEV_VENV_PATH="${PWD}/.cache/scripts/.venv" \
  TARGET_VENV_PATH="${PWD}/.cache/scripts/.fastapi_mgmt_ui-dev-venv" \
  bash "${PROJ_PATH}/scripts/utilities/ensure-reqs2.sh"

python -m mypy "${PROJ_PATH}/comfy_fulcrum/fastapi_mgmt_ui" "${PROJ_PATH}/comfy_fulcrum/base" "${PROJ_PATH}/comfy_fulcrum/private" --check-untyped-defs --show-error-codes
python3 -m pyright --stats "${PROJ_PATH}/comfy_fulcrum/fastapi_mgmt_ui" "${PROJ_PATH}/comfy_fulcrum/base" "${PROJ_PATH}/comfy_fulcrum/private"

echo -e "${GREEN}All type checks ran successfully${NC}"
