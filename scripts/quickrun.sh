#!/bin/bash
# https://gist.github.com/mohanpedala/1e2ff5661761d3abd0385e8223e16425
set -e -x -v -u -o pipefail

SCRIPT_DIR=$(realpath "$(dirname "${BASH_SOURCE[0]}")")
source "${SCRIPT_DIR}/utilities/common.sh"

################################################################################

VENV_PATH="${PWD}/.cache/scripts/.cli-prod-venv" source "${PROJ_PATH}/scripts/utilities/ensure-venv.sh"
TOML=${PROJ_PATH}/pyproject.toml EXTRAS=cli,prod PIN=cli_prod_pinned \
  DEV_VENV_PATH="${PWD}/.cache/scripts/.venv" \
  TARGET_VENV_PATH="${PWD}/.cache/scripts/.cli-prod-venv" \
  bash "${PROJ_PATH}/scripts/utilities/ensure-reqs2.sh"

python -m comfy_fulcrum.cli --help

echo -e "${GREEN}Quick run ran successfully${NC}"
